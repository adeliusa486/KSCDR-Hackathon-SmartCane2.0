#!/usr/bin/env python3
"""Smart cane - step 1 detector: camera -> Hailo NPU -> named objects.

This is the vision half of the cane, on its own. No ToF, no vibration, no
speech yet. It prints the sentence fragments that the speech layer will read out
later, so the output format is already the one we want.

    python3 detect.py                          # headless, prints detections
    python3 detect.py --preview                # draw boxes in a window
    python3 detect.py --conf 0.5 --interval 1  # quieter, one report per second
    python3 detect.py --model /usr/share/hailo-models/yolov6n.hef
    python3 detect.py --corridor 15            # wider 'ahead' cone

Camera defaults assume the Arducam B0310: Sony IMX708 behind a 120 deg (H) M12
lens. If you swap the lens, pass the new figure with --hfov or every
left/ahead/right call will be wrong.

Run with the system Python (picamera2 and hailo_platform come from apt).
"""

import argparse
import glob
import math
import os
import sys
import time
from collections import namedtuple

HERE = os.path.dirname(os.path.abspath(__file__))

# Models that ship with `hailo-all`, best first for our use.
# yolov8s is the accuracy/speed sweet spot on the Hailo-8L; yolov6n is faster.
MODEL_PREFERENCE = [
    "/usr/share/hailo-models/yolov8s_h8l.hef",
    "/usr/share/hailo-models/yolov8s.hef",
    "/usr/share/hailo-models/yolov6n.hef",
    "/usr/share/hailo-models/yolox_s_leaky_h8l_mz.hef",
]

# Classes that matter to someone walking. Everything else is noise on the street.
# Order is roughly by how urgently it should be announced.
PRIORITY = [
    "person", "car", "motorcycle", "bus", "truck", "bicycle", "train",
    "dog", "cow", "horse", "traffic light", "stop sign", "bench", "chair",
    "potted plant", "fire hydrant", "backpack", "suitcase",
]

Detection = namedtuple("Detection", "label score x0 y0 x1 y1")


def pick_model(explicit):
    if explicit:
        if not os.path.exists(explicit):
            sys.exit(f"Model not found: {explicit}")
        return explicit
    for path in MODEL_PREFERENCE:
        if os.path.exists(path):
            return path
    found = sorted(glob.glob("/usr/share/hailo-models/*.hef"))
    if found:
        return found[0]
    sys.exit(
        "No .hef model found in /usr/share/hailo-models/.\n"
        "Install the Hailo stack first:  sudo apt install hailo-all"
    )


def load_labels(path):
    if not os.path.exists(path):
        sys.exit(f"Label file not found: {path}")
    with open(path) as fh:
        return [line.strip() for line in fh if line.strip()]


def bearing(x0, x1, width, hfov):
    """Horizontal angle of the box centre, in degrees, negative = left.

    Rectilinear approximation. The B0310's M12 lens has real barrel distortion at
    120 deg, so edge angles are optimistic. Good enough for left/ahead/right.
    """
    offset = ((x0 + x1) / 2 / width) - 0.5          # -0.5 .. +0.5 of frame
    half = math.tan(math.radians(hfov / 2.0))
    return math.degrees(math.atan(2 * offset * half))


def zone(x0, x1, width, hfov, corridor_deg):
    """Which way to turn: left, ahead, or right.

    'ahead' means inside the walking corridor, not merely near the middle of the
    frame. With the B0310's 120 deg lens a fixed fraction of frame width is far
    too wide: the middle 24% of the frame spans about 28 deg, which would call a
    car two lanes over 'ahead'. So the split is done in degrees instead.
    """
    b = bearing(x0, x1, width, hfov)
    if b < -corridor_deg:
        return "left"
    if b > corridor_deg:
        return "right"
    return "ahead"


def nearness(y0, y1, height):
    """Very rough distance proxy from how tall the box is in the frame.

    This is NOT a distance measurement. A real number comes from the ToF sensor
    in step 2. It is here so the output sentence already has the right shape.
    """
    frac = (y1 - y0) / height
    if frac > 0.55:
        return "close"
    if frac > 0.25:
        return "near"
    return "far"


def extract_detections(raw, labels, width, height, threshold):
    """Decode the Hailo NMS output.

    Models built with on-chip NMS return one list per class, each entry being
    [y0, x0, y1, x1, score] in normalised coordinates.
    """
    out = []
    for class_id, dets in enumerate(raw):
        if class_id >= len(labels):
            continue
        for det in dets:
            score = float(det[4])
            if score < threshold:
                continue
            y0, x0, y1, x1 = (float(v) for v in det[:4])
            out.append(
                Detection(
                    labels[class_id],
                    score,
                    x0 * width,
                    y0 * height,
                    x1 * width,
                    y1 * height,
                )
            )
    return out


def rank(dets, width, height, only_priority):
    """Most important first: priority class, then nearest, then most confident."""

    def key(d):
        try:
            pri = PRIORITY.index(d.label)
        except ValueError:
            pri = len(PRIORITY)
        area = ((d.x1 - d.x0) * (d.y1 - d.y0)) / (width * height)
        return (pri, -area, -d.score)

    if only_priority:
        dets = [d for d in dets if d.label in PRIORITY]
    return sorted(dets, key=key)


def describe(dets, width, height, limit, hfov, corridor_deg):
    """Build the fragments the speech layer will eventually read out.

    Each fragment carries its confidence as a trailing "@0.87". The speech
    layer needs it to decide whether to trust the label enough to say the name,
    or to fall back to announcing it as a generic obstacle. Running the
    detector at a low threshold and deciding later is what lets us miss almost
    nothing without also announcing nonsense names.
    """
    parts = []
    for d in dets[:limit]:
        where = zone(d.x0, d.x1, width, hfov, corridor_deg)
        parts.append(
            f"{d.label} {where}, {nearness(d.y0, d.y1, height)} @{d.score:.2f}"
        )
    return " | ".join(parts) if parts else "clear"


class Trace:
    """One CSV row per frame with the time each stage finished.

    Clocks: every *_ns column is time.monotonic_ns(). sensor_ts_ns is the
    camera's own SensorTimestamp from the frame metadata, on the kernel clock
    libcamera uses, and boottime_minus_mono_ns is the offset between
    CLOCK_BOOTTIME and CLOCK_MONOTONIC at that moment. Which clock and which
    instant (exposure start or readout) SensorTimestamp means is to be
    confirmed on the Pi in Step 3.0. With both columns logged, the
    photon-to-frame delay can be worked out either way.
    """

    COLUMNS = ("frame,sensor_ts_ns,boottime_minus_mono_ns,capture_ns,"
               "frame_ready_ns,inference_end_ns,postprocess_end_ns,"
               "report_ns,detections,exposure_us,analogue_gain")

    def __init__(self, path):
        self.f = open(path, "w", buffering=1 << 16)
        self.f.write(self.COLUMNS + "\n")

    def row(self, n, meta, t_cap, t_ready, t_inf, t_post, t_report, ndet):
        meta = meta or {}
        offset = time.clock_gettime_ns(time.CLOCK_BOOTTIME) - time.monotonic_ns()
        self.f.write(f"{n},{meta.get('SensorTimestamp', '')},{offset},{t_cap},"
                     f"{t_ready},{t_inf},{t_post},{t_report},{ndet},"
                     f"{meta.get('ExposureTime', '')},{meta.get('AnalogueGain', '')}\n")

    def close(self):
        self.f.close()


def main():
    ap = argparse.ArgumentParser(description="Smart cane vision test: camera -> Hailo -> objects")
    ap.add_argument("--model", help="path to a .hef file (default: best one installed)")
    ap.add_argument("--labels", default=os.path.join(HERE, "coco.txt"))
    ap.add_argument("--conf", type=float, default=0.4, help="confidence threshold")
    ap.add_argument("--interval", type=float, default=0.0,
                    help="seconds between printed reports (0 = every frame)")
    ap.add_argument("--limit", type=int, default=4, help="max objects per report")
    ap.add_argument("--all-classes", action="store_true",
                    help="report every COCO class, not just the walking-relevant ones")
    ap.add_argument("--preview", action="store_true", help="show a window with boxes")
    ap.add_argument("--hfov", type=float, default=120.0,
                    help="camera horizontal field of view in degrees "
                         "(Arducam B0310 / IMX708 with the stock M12 lens is 120)")
    ap.add_argument("--corridor", type=float, default=10.0,
                    help="half-width of the 'ahead' walking corridor, in degrees")
    ap.add_argument("--fps", type=int, default=15,
                    help="camera frame rate. LOWER means a longer exposure "
                         "per frame, which is what fixes flaky detection in "
                         "dim light. We are never fps limited.")
    ap.add_argument("--ev", type=float, default=0.7,
                    help="exposure bias in stops. Positive brightens. Wide "
                         "street scenes full of sky need this.")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--trace", metavar="CSV",
                    help="write one timing row per frame (Phase 3 Step 3.0). "
                         "Summarise with tools/trace_summary.py")
    ap.add_argument("--frames", type=int, default=0,
                    help="stop after this many frames, 0 = run until ctrl-c")
    args = ap.parse_args()

    try:
        from picamera2 import Picamera2
        from picamera2.devices import Hailo
    except ImportError as exc:
        sys.exit(
            f"{exc}\n"
            "Run with the system Python. picamera2 and hailo_platform are apt\n"
            "packages, not PyPI ones. If you need a venv:\n"
            "  python3 -m venv --system-site-packages ~/smartcane/venv"
        )

    model = pick_model(args.model)
    labels = load_labels(args.labels)
    print(f"model  : {model}")
    print(f"labels : {len(labels)} classes")

    with Hailo(model) as hailo:
        in_h, in_w, _ = hailo.get_input_shape()
        print(f"input  : {in_w}x{in_h}")

        picam2 = Picamera2()
        # main = what we look at / record, lores = what the NPU eats.
        # Feeding the NPU a small stream keeps the ISP from doing pointless work.
        # Low light is the single biggest cause of flaky detections indoors and
        # at dusk. A dark, noisy frame gives YOLO nothing to lock onto, so
        # confidence collapses and objects flicker in and out even though the
        # object never moved.
        #
        # We trade frame rate for light on purpose. At 15 fps the sensor can
        # integrate twice as long per frame as at 30, and we were never
        # frame-rate limited anyway: the NPU takes 13 ms and we only report
        # about once a second. Brightness matters far more than fps here.
        controls = {
            "FrameRate": args.fps,
            "AeEnable": True,
            "AwbEnable": True,
            # Bias auto-exposure brighter than the meter wants. Wide-angle
            # street scenes are full of bright sky that drags everything else
            # into shadow.
            "ExposureValue": args.ev,
            # Let the sensor use long exposures when it needs to, up to
            # 1/(fps) seconds.
            "FrameDurationLimits": (int(1e6 / args.fps), int(1e6 / args.fps)),
            "AeExposureMode": 0,
            # Slight noise reduction helps YOLO more than it hurts, because
            # sensor noise at high gain looks like texture.
            "NoiseReductionMode": 2,
        }
        config = picam2.create_preview_configuration(
            main={"size": (args.width, args.height), "format": "XRGB8888"},
            lores={"size": (in_w, in_h), "format": "RGB888"},
            controls=controls,
        )
        picam2.configure(config)
        picam2.start()
        # Give auto-exposure and auto-white-balance time to converge. Frames
        # grabbed in the first second are dark and wrongly coloured, which is
        # exactly when a user is pointing the cane at something and expecting
        # an answer.
        time.sleep(1.5)
        if args.preview:
            picam2.start_preview()

        print("running. ctrl-c to stop.\n")

        trace = Trace(args.trace) if args.trace else None
        frames = 0
        total = 0
        fps = 0.0
        t_fps = time.monotonic()
        t_report = 0.0
        try:
            while not args.frames or total < args.frames:
                # capture_request + make_array is what capture_array does
                # inside. Done by hand so the frame's metadata (sensor
                # timestamp) is available for the trace.
                request = picam2.capture_request()
                t_cap = time.monotonic_ns()
                frame = request.make_array("lores")
                meta = request.get_metadata() if trace else None
                request.release()
                t_ready = time.monotonic_ns()
                raw = hailo.run(frame)
                t_inf = time.monotonic_ns()
                dets = extract_detections(raw, labels, args.width, args.height, args.conf)
                dets = rank(dets, args.width, args.height, not args.all_classes)
                t_post = time.monotonic_ns()

                frames += 1
                total += 1
                now = time.monotonic()
                if now - t_fps >= 1.0:
                    fps = frames / (now - t_fps)
                    frames = 0
                    t_fps = now

                reported = now - t_report >= args.interval
                if reported:
                    t_report = now
                    line = describe(dets, args.width, args.height, args.limit,
                                    args.hfov, args.corridor)
                    print(f"[{fps:5.1f} fps]  {line}")
                if trace:
                    trace.row(total, meta, t_cap, t_ready, t_inf, t_post,
                              time.monotonic_ns() if reported else 0, len(dets))
        except KeyboardInterrupt:
            print("\nstopped.")
        finally:
            picam2.stop()
            if trace:
                trace.close()


if __name__ == "__main__":
    main()
