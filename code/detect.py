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
    python3 detect.py --rotate 90              # camera mounted on its side

Camera defaults assume the Arducam B0310: Sony IMX708 behind a 120 deg (H) M12
lens (--lens-hfov). The sensor mode Picamera2 picks for 1280x720 is a centre
crop, so the real field of view is worked out from the crop at start-up. Pass
--hfov only to override that.

What the model sees must match what it was trained on, or confidence drops
and chairs and tables turn into "obstacle":
  - upright: --rotate turns a sideways or upside-down camera mount upright,
  - R, G, B channel order (Ultralytics trains on RGB),
  - undistorted: the 16:9 frame is letterboxed into the square input with
    grey bars, as Ultralytics does in validation, not squeezed 1.78x.

Run with the system Python (picamera2 and hailo_platform come from apt).
"""

import argparse
import glob
import math
import os
import signal
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
    # smartcane152 drop-offs first: a fall is the worst outcome. Unknown to
    # the COCO models, so harmless there.
    "open hole", "stairs", "pothole", "manhole", "curb", "rail track",
    "traffic cone", "barrier", "bollard",
    "person", "car", "motorcycle", "bus", "truck", "bicycle", "train",
    "dog", "cow", "horse", "traffic light", "stop sign", "bench", "chair",
    "potted plant", "fire hydrant", "backpack", "suitcase",
]

Detection = namedtuple("Detection", "label score x0 y0 x1 y1")

# Picamera2 names formats after DRM fourcc codes, which list the bytes in
# reverse: "RGB888" arrives as B, G, R and "BGR888" as R, G, B. The model was
# trained and calibrated on R, G, B, so the lores stream asks for "BGR888".
# tools/vision_probe.py checks this on the real camera.
LORES_FORMAT = "BGR888"
PAD_VALUE = 114          # Ultralytics' letterbox grey

# Typical real height in metres, for a rough camera-only distance:
# distance = real height x focal length / box height. Only used when the box
# is not cut off by the frame edge. Good to about +-30 %, so it is spoken as
# "about N meters" and never replaces a ToF reading. Classes without a stable
# height (poles, walls, stairs, holes) get no estimate.
TYPICAL_HEIGHT_M = {
    "person": 1.65, "child": 1.1, "cyclist": 1.7, "motorcyclist": 1.6,
    "wheelchair": 1.2, "stroller": 1.0, "dog": 0.55, "cat": 0.3,
    "cow": 1.4, "horse": 1.6, "goat": 0.7, "sheep": 0.8, "camel": 2.0,
    "car": 1.5, "taxi": 1.5, "van": 2.0, "ambulance": 2.4, "bus": 3.1,
    "truck": 3.0, "motorcycle": 1.1, "bicycle": 1.0, "e-scooter": 1.1,
    "traffic cone": 0.7, "bollard": 0.9, "fire hydrant": 0.7, "barrel": 0.9,
    "trash can": 1.0, "bench": 0.8, "mailbox": 1.1, "utility box": 1.2,
    "parking meter": 1.4, "potted plant": 0.7, "wet floor sign": 0.6,
    "door": 2.05, "chair": 0.9, "stool": 0.65, "couch": 0.85, "bed": 0.6,
    "table": 0.75, "desk": 0.75, "coffee table": 0.45, "nightstand": 0.6,
    "chest of drawers": 0.9, "wardrobe": 1.9, "bookcase": 1.8,
    "cabinet": 0.9, "refrigerator": 1.75, "washing machine": 0.85,
    "toilet": 0.75, "sink": 0.9, "stove": 0.9, "oven": 0.9,
    "backpack": 0.45, "suitcase": 0.65, "box": 0.4, "ladder": 1.8,
    "elevator": 2.1, "atm": 1.6, "kiosk": 2.0,
}

# SIGUSR1 asks for one full-resolution JPEG of the current view, for the AI
# assistant. It lands in RAM (/dev/shm), not on the SD card. Written to a temp
# name and renamed, so a reader never sees half a file.
SNAPSHOT = "/dev/shm/cane_snapshot.jpg"
_snapshot_wanted = False


def _want_snapshot(signum, frame):
    global _snapshot_wanted
    _snapshot_wanted = True


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


def effective_hfov(lens_hfov, crop_w, full_w):
    """Horizontal FOV of a centre crop of the sensor, in degrees.

    Picamera2 picks the IMX708's 1536x864 mode for a 1280x720 stream, and that
    mode reads only the middle 3072 of 4608 pixel columns. Measured on 2 Oct
    2026: a 120 deg lens then sees about 98 deg, not 120. Straight-lens
    arithmetic on a barrel-distorted lens, so an estimate.
    """
    half = math.tan(math.radians(lens_hfov / 2.0)) * crop_w / float(full_w)
    return math.degrees(2 * math.atan(half))


def upright_fov(hfov, width, height, rotate):
    """Horizontal FOV of the picture after --rotate. A camera on its side
    looks across the world with its short (vertical) side."""
    if rotate % 180 == 0:
        return hfov
    half = math.tan(math.radians(hfov / 2.0)) * height / float(width)
    return math.degrees(2 * math.atan(half))


def lores_size(width, height, in_w, in_h):
    """Lores stream size: the main frame scaled to fit the model input with
    its aspect ratio kept, rounded down to even numbers for the ISP. Rotation
    does not change it: a 640x360 frame turned on its side is 360x640, which
    fits a 640x640 input just as well."""
    s = min(in_w / float(width), in_h / float(height))
    return int(width * s) // 2 * 2, int(height * s) // 2 * 2


def prepare(frame, in_w, in_h, rotate=0, fit="letterbox", out=None):
    """Turn a camera frame into the model input.

    Returns (input array, region). region = (x0, y0, w, h) is where the
    picture sits inside the input, as fractions of the input size, so boxes
    can be mapped back. fit="stretch" is the old behaviour (squeeze to the
    input size, region = whole input), kept for A/B tests.

    out: a (in_h, in_w, 3) uint8 array to fill and return. Pass the same one
    every frame, so the loop does not allocate 1.2 MB per frame.
    """
    import numpy as np
    if out is None:
        out = np.empty((in_h, in_w, 3), dtype=np.uint8)
    if rotate:
        # np.rot90 turns counter-clockwise for positive k. --rotate is the
        # clockwise turn that makes the picture upright.
        frame = np.rot90(frame, k=-(rotate // 90) % 4)
    h, w = frame.shape[:2]
    if fit == "stretch" or (w, h) == (in_w, in_h):
        if (w, h) != (in_w, in_h):
            from PIL import Image
            frame = np.asarray(Image.fromarray(np.ascontiguousarray(frame[:, :, :3]))
                               .resize((in_w, in_h), Image.BILINEAR))
        out[:] = frame[:, :, :3]
        return out, (0.0, 0.0, 1.0, 1.0)
    if w > in_w or h > in_h:
        from PIL import Image
        s = min(in_w / float(w), in_h / float(h))
        w, h = max(2, int(w * s)), max(2, int(h * s))
        frame = np.asarray(Image.fromarray(np.ascontiguousarray(frame[:, :, :3]))
                           .resize((w, h), Image.BILINEAR))
    out[:] = PAD_VALUE
    x, y = (in_w - w) // 2, (in_h - h) // 2
    out[y:y + h, x:x + w] = frame[:, :, :3]
    return out, (x / float(in_w), y / float(in_h), w / float(in_w), h / float(in_h))


def bearing(x0, x1, width, hfov):
    """Horizontal angle of the box centre, in degrees, negative = left.

    Rectilinear approximation. The B0310's M12 lens has real barrel distortion,
    so edge angles are optimistic. Good enough for left/ahead/right.
    """
    return angle_at((x0 + x1) / 2.0, width, hfov)


def angle_at(x, width, hfov):
    offset = x / width - 0.5                       # -0.5 .. +0.5 of frame
    half = math.tan(math.radians(hfov / 2.0))
    return math.degrees(math.atan(2 * offset * half))


def zone(x0, x1, width, hfov, corridor_deg):
    """Which way to turn: left, ahead, or right.

    'ahead' means in the walking path: the box centre is inside the corridor,
    or the box spans the line straight ahead of the camera (a table whose
    middle is off to one side still blocks the path if its edge crosses it).
    The split is in degrees, not frame fractions, so it does not change with
    the lens. Directions are the CAMERA's: if someone faces the cane, their
    left is the cane's right.
    """
    if angle_at(x0, width, hfov) < 0 < angle_at(x1, width, hfov):
        return "ahead"
    b = bearing(x0, x1, width, hfov)
    if b < -corridor_deg:
        return "left"
    if b > corridor_deg:
        return "right"
    return "ahead"


def estimate_m(d, width, height, hfov):
    """Rough distance in metres from the box height, or None.

    Pinhole camera: distance = real height x focal length / box height. Only
    for classes with a typical height, and only when the box is not cut by the
    top or bottom edge (a cut box makes the object look smaller, so the
    estimate would be too far, the unsafe direction).
    """
    real = TYPICAL_HEIGHT_M.get(d.label)
    box_h = d.y1 - d.y0
    if real is None or box_h <= 0:
        return None
    edge = 0.02 * height
    if d.y0 <= edge or d.y1 >= height - edge:
        return None
    focal = (width / 2.0) / math.tan(math.radians(hfov / 2.0))
    return real * focal / box_h


def iou(a, b):
    ix = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
    iy = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
    inter = ix * iy
    union = ((a.x1 - a.x0) * (a.y1 - a.y0) + (b.x1 - b.x0) * (b.y1 - b.y0)
             - inter)
    return inter / union if union > 0 else 0.0


def dedupe(dets, thresh=0.7):
    """One object, one name. The NMS inside the HEF runs per class, so the
    same table can come back as "table" and "desk", or a person as "person"
    and "child". Keep the most confident of any boxes that overlap this much."""
    kept = []
    for d in sorted(dets, key=lambda d: -d.score):
        if all(iou(d, k) < thresh for k in kept):
            kept.append(d)
    return kept


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


def extract_detections(raw, labels, width, height, threshold,
                       region=(0.0, 0.0, 1.0, 1.0)):
    """Decode the Hailo NMS output.

    Models built with on-chip NMS return one list per class, each entry being
    [y0, x0, y1, x1, score] in normalised coordinates of the model input.
    region (from prepare()) maps them back to the picture: boxes that lie
    only on the letterbox bars are dropped, the rest are clipped.
    """
    rx, ry, rw, rh = region
    out = []
    for class_id, dets in enumerate(raw):
        if class_id >= len(labels):
            continue
        for det in dets:
            score = float(det[4])
            if score < threshold:
                continue
            y0, x0, y1, x1 = (float(v) for v in det[:4])
            x0, x1 = (min(1.0, max(0.0, (v - rx) / rw)) for v in (x0, x1))
            y0, y1 = (min(1.0, max(0.0, (v - ry) / rh)) for v in (y0, y1))
            if x1 <= x0 or y1 <= y0:
                continue
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

    When the box gives a camera distance estimate it follows the size word
    in metres: "chair left, near 2.4m @0.81".
    """
    parts = []
    for d in dets[:limit]:
        where = zone(d.x0, d.x1, width, hfov, corridor_deg)
        m = estimate_m(d, width, height, hfov)
        dist = nearness(d.y0, d.y1, height) + (f" {m:.1f}m" if m else "")
        parts.append(f"{d.label} {where}, {dist} @{d.score:.2f}")
    return " | ".join(parts) if parts else "clear"


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
    ap.add_argument("--stream-file", metavar="JPEG",
                    help="demo mode: write every frame, boxes drawn, to this "
                         "JPEG (plus a .json of the detections next to it) "
                         "for the laptop dashboard. Off by default, zero cost.")
    ap.add_argument("--lens-hfov", type=float, default=120.0,
                    help="lens horizontal FOV over the FULL sensor width "
                         "(Arducam B0310 / IMX708 with the stock M12 lens is 120)")
    ap.add_argument("--hfov", type=float, default=0.0,
                    help="override the field of view of the picture, degrees. "
                         "0 = work it out from the sensor crop (about 98)")
    ap.add_argument("--corridor", type=float, default=15.0,
                    help="half-width of the 'ahead' walking corridor, in degrees")
    ap.add_argument("--rotate", type=int, default=0, choices=(0, 90, 180, 270),
                    help="clockwise turn that makes the camera picture "
                         "upright. Set it from tools/vision_probe.py --orient "
                         "with the cane held as when walking")
    ap.add_argument("--fit", choices=("letterbox", "stretch"),
                    default="letterbox",
                    help="letterbox keeps the shapes the model was trained "
                         "on. stretch is the old 1.78x squeeze, for A/B tests")
    ap.add_argument("--lores-format", default=LORES_FORMAT,
                    help="Picamera2 lores format. BGR888 gives R,G,B bytes")
    ap.add_argument("--fps", type=int, default=15,
                    help="camera frame rate. LOWER means a longer exposure "
                         "per frame, which is what fixes flaky detection in "
                         "dim light. We are never fps limited.")
    ap.add_argument("--ev", type=float, default=0.7,
                    help="exposure bias in stops. Positive brightens. Wide "
                         "street scenes full of sky need this.")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    args = ap.parse_args()

    # Install the snapshot handler first. SIGUSR1's default action is to
    # terminate, and the Hailo and camera take seconds to start: a button
    # press in that window used to kill detect.py (found 8 Oct 2026).
    global _snapshot_wanted
    signal.signal(signal.SIGUSR1, _want_snapshot)

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

        picam2, (lw, lh) = open_camera(Picamera2, args, in_w, in_h)
        hfov = args.hfov or camera_hfov(picam2, args.lens_hfov)
        # Geometry is done on the upright picture.
        W, H = ((args.width, args.height) if args.rotate % 180 == 0
                else (args.height, args.width))
        hfov_up = upright_fov(hfov, args.width, args.height, args.rotate)
        print(f"lores  : {lw}x{lh} {args.lores_format}, fit {args.fit}, "
              f"rotate {args.rotate}")
        print(f"fov    : {hfov:.1f} deg camera, {hfov_up:.1f} deg across the "
              f"upright picture, ahead = +-{args.corridor:g} deg")
        if args.preview:
            picam2.start_preview()

        viewer = None
        if args.stream_file:
            from demo_view import Viewer
            def info(d):
                return {"zone": zone(d.x0, d.x1, W, hfov_up, args.corridor),
                        "near": nearness(d.y0, d.y1, H),
                        "est_m": estimate_m(d, W, H, hfov_up),
                        "bearing": bearing(d.x0, d.x1, W, hfov_up)}
            viewer = Viewer(args.stream_file, W, H, hfov_up, args.corridor, info)
        print("running. ctrl-c to stop.\n")

        import numpy as np
        inbuf = np.empty((in_h, in_w, 3), dtype=np.uint8)   # see prepare()
        frames = 0
        fps = 0.0
        t_fps = time.monotonic()
        t_report = 0.0
        try:
            while True:
                if _snapshot_wanted:
                    _snapshot_wanted = False
                    try:
                        save_snapshot(picam2, args.rotate)
                    except Exception as exc:
                        print(f"snapshot failed: {exc}", file=sys.stderr)
                view = None
                if viewer is not None and viewer.due():
                    # Both streams from one request, so the boxes drawn on
                    # the main frame belong to exactly this picture.
                    req = picam2.capture_request()
                    try:
                        frame = req.make_array("lores")
                        view = req.make_array("main")
                    finally:
                        req.release()
                    if args.rotate:
                        import numpy as np
                        view = np.rot90(view, k=-(args.rotate // 90) % 4)
                else:
                    frame = picam2.capture_array("lores")
                inp, region = prepare(frame, in_w, in_h, args.rotate, args.fit,
                                     inbuf)
                t_inf = time.perf_counter()
                raw = hailo.run(inp)
                infer_ms = 1000 * (time.perf_counter() - t_inf)
                dets = extract_detections(raw, labels, W, H, args.conf, region)
                dets = rank(dedupe(dets), W, H, not args.all_classes)
                if view is not None:
                    # The demo view must never be able to stop the cane.
                    try:
                        viewer.write(view, dets, fps, infer_ms)
                    except Exception as exc:
                        print(f"demo view failed: {exc}", file=sys.stderr)

                frames += 1
                now = time.monotonic()
                if now - t_fps >= 1.0:
                    fps = frames / (now - t_fps)
                    frames = 0
                    t_fps = now

                if now - t_report >= args.interval:
                    t_report = now
                    line = describe(dets, W, H, args.limit, hfov_up,
                                    args.corridor)
                    print(f"[{fps:5.1f} fps]  {line}")
        except KeyboardInterrupt:
            print("\nstopped.")
        finally:
            picam2.stop()


def open_camera(Picamera2, args, in_w, in_h):
    """Configure and start the camera the way the cane uses it. Shared with
    tools/vision_probe.py so the probe measures exactly what the cane sees.
    Returns (picam2, lores size)."""
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
    # The lores stream keeps the main stream's 16:9 shape (640x360), and
    # prepare() pads it to the square model input. A model-sized lores
    # stream would squeeze every object 1.78x sideways.
    if args.fit == "letterbox":
        lw, lh = lores_size(args.width, args.height, in_w, in_h)
    else:
        lw, lh = in_w, in_h
    config = picam2.create_preview_configuration(
        main={"size": (args.width, args.height), "format": "XRGB8888"},
        lores={"size": (lw, lh), "format": args.lores_format},
        controls=controls,
    )
    picam2.configure(config)
    picam2.start()
    # Give auto-exposure and auto-white-balance time to converge. Frames
    # grabbed in the first second are dark and wrongly coloured, which is
    # exactly when a user is pointing the cane at something and expecting
    # an answer.
    time.sleep(1.5)
    return picam2, (lw, lh)


def camera_hfov(picam2, lens_hfov):
    """Real horizontal FOV of the running stream, from the sensor crop."""
    try:
        crop = picam2.capture_metadata()["ScalerCrop"]
        full_w = picam2.camera_properties["PixelArraySize"][0]
        return effective_hfov(lens_hfov, crop[2], full_w)
    except Exception as exc:
        print(f"could not read the sensor crop ({exc}), assuming the full "
              f"lens FOV", file=sys.stderr)
        return lens_hfov


def save_snapshot(picam2, rotate):
    """Full-resolution JPEG of the current view for the AI assistant,
    turned upright like the detection frames."""
    img = picam2.capture_image("main").convert("RGB")
    if rotate:
        from PIL import Image
        img = img.transpose({90: Image.Transpose.ROTATE_270,
                             180: Image.Transpose.ROTATE_180,
                             270: Image.Transpose.ROTATE_90}[rotate])
    img.save(SNAPSHOT + ".tmp", "JPEG", quality=90)
    os.replace(SNAPSHOT + ".tmp", SNAPSHOT)


if __name__ == "__main__":
    main()
