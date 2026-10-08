#!/usr/bin/env python3
"""Smart cane - check what the model really gets from the camera.

Three questions, answered on the live camera with detect.py's own settings
(open_camera, prepare). The camera and the Hailo must be free, so stop the
service first.

  1. Colour order. Picamera2 format names list bytes in reverse, so the lores
     stream is compared against a correctly coloured image of the same frame.
  2. Field of view. Sensor mode, ScalerCrop and the FOV that follows.
  3. --orient: which --rotate makes the picture upright. Hold the cane as when
     walking, pointed at a room or street with things in it. Every frame is
     run through the model at 0, 90, 180 and 270 degrees. Upright pictures
     give the most confident detections, by a wide margin.

    systemctl --user stop smartcane
    python3 tools/vision_probe.py --model models/smartcane152_v3_h8l.hef \
        --labels models/smartcane152.txt --orient --frames 30 --out /tmp/probe
    systemctl --user start smartcane
"""
import argparse
import os
import sys
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import detect  # noqa: E402


def channel_order(lores, main_rgb):
    """'RGB' or 'BGR': which way round the lores bytes are. Compares the
    red-minus-blue difference of the two pictures pixel by pixel."""
    from PIL import Image
    small = np.asarray(Image.fromarray(main_rgb).resize(
        (lores.shape[1], lores.shape[0]), Image.BILINEAR)).astype(float)
    lo = lores[:, :, :3].astype(float)
    ref = small[:, :, 0] - small[:, :, 2]
    as_rgb = np.corrcoef(ref.ravel(), (lo[:, :, 0] - lo[:, :, 2]).ravel())[0, 1]
    return ("RGB" if as_rgb > 0 else "BGR"), as_rgb


def score(dets):
    """Sum of the best confidences: high when the model recognises things."""
    return sum(sorted((d.score for d in dets), reverse=True)[:5])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--fps", type=int, default=10)
    ap.add_argument("--ev", type=float, default=0.7)
    ap.add_argument("--lores-format", default=detect.LORES_FORMAT)
    ap.add_argument("--orient", action="store_true")
    ap.add_argument("--frames", type=int, default=20)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--out", default="/tmp/probe", help="path prefix for JPEGs")
    args = ap.parse_args()

    from picamera2 import Picamera2
    from picamera2.devices import Hailo
    from PIL import Image

    labels = detect.load_labels(args.labels)
    cam_args = SimpleNamespace(fps=args.fps, ev=args.ev, width=1280, height=720,
                               fit="letterbox", lores_format=args.lores_format)
    with Hailo(args.model) as hailo:
        in_h, in_w, _ = hailo.get_input_shape()
        picam2, (lw, lh) = detect.open_camera(Picamera2, cam_args, in_w, in_h)
        try:
            cfg = picam2.camera_configuration()
            md = picam2.capture_metadata()
            full = picam2.camera_properties["PixelArraySize"]
            hfov = detect.camera_hfov(picam2, 120.0)
            print(f"sensor mode : {cfg['sensor']}")
            print(f"ScalerCrop  : {md.get('ScalerCrop')} of {full}")
            print(f"FOV         : {hfov:.1f} deg (lens 120 over the full width)")
            print(f"exposure    : {md.get('ExposureTime')} us, gain "
                  f"{md.get('AnalogueGain', 0):.1f}, lux {md.get('Lux', 0):.0f}")

            req = picam2.capture_request()
            try:
                lores = req.make_array("lores")
                main_rgb = np.asarray(req.make_image("main").convert("RGB"))
            finally:
                req.release()
            order, r = channel_order(lores, main_rgb)
            print(f"lores {args.lores_format} {lw}x{lh}: bytes are {order} "
                  f"(correlation {r:+.2f}). The model wants RGB.")
            Image.fromarray(main_rgb).save(args.out + "_main.jpg", quality=85)

            if args.orient:
                inbuf = np.empty((in_h, in_w, 3), dtype=np.uint8)
                totals = {0: 0.0, 90: 0.0, 180: 0.0, 270: 0.0}
                names = {k: {} for k in totals}
                for _ in range(args.frames):
                    frame = picam2.capture_array("lores")
                    if order == "BGR":
                        frame = frame[:, :, ::-1]
                    for rot in totals:
                        inp, region = detect.prepare(frame, in_w, in_h, rot,
                                                     out=inbuf)
                        dets = detect.dedupe(detect.extract_detections(
                            hailo.run(inp), labels, 1.0, 1.0, args.conf, region))
                        totals[rot] += score(dets)
                        for d in dets:
                            names[rot][d.label] = max(names[rot].get(d.label, 0), d.score)
                best = max(totals, key=totals.get)
                print(f"\norientation over {args.frames} frames "
                      f"(sum of top-5 confidences per frame):")
                for rot in sorted(totals):
                    top = sorted(names[rot].items(), key=lambda kv: -kv[1])[:6]
                    seen = ", ".join(f"{n} {s:.2f}" for n, s in top) or "nothing"
                    mark = "  <- best" if rot == best else ""
                    print(f"  --rotate {rot:3d}: {totals[rot] / args.frames:5.2f}"
                          f"  [{seen}]{mark}")
                img = Image.fromarray(main_rgb)
                if best:
                    img = img.transpose({90: Image.Transpose.ROTATE_270,
                                         180: Image.Transpose.ROTATE_180,
                                         270: Image.Transpose.ROTATE_90}[best])
                img.save(args.out + "_upright.jpg", quality=85)
                print(f"\nsuggested: --rotate {best}  (picture: {args.out}_upright.jpg)")
        finally:
            picam2.stop()


if __name__ == "__main__":
    main()
