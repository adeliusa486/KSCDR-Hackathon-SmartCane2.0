#!/usr/bin/env python3
"""OmniWalk - run street photos through the cane's own vision path and save
the dashboard frames, for the website's example and pictures.

Same steps as detect.py for a camera frame: centre-crop to 16:9, 1280x720
main picture, 640x360 lores letterboxed into the model, the cane's HEF on the
Hailo, the same decoder, dedupe and ranking, the same confidence threshold,
and demo_view.Viewer to draw. Nothing is drawn by hand: every box, name,
confidence and distance is what the cane reports for that picture.

Stop the cane first (the Hailo serves one process at a time):

    systemctl --user stop smartcane
    python3 tools/photo_demo.py --out ~/photo_demo photos/*.jpg
    systemctl --user start smartcane

Writes <out>/<name>.jpg and <name>.json (the dashboard's detection format)
plus <out>/examples.json for the website (web/replay/).
"""
import argparse
import json
import os
import sys
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from detect import (bearing, dedupe, describe, estimate_m, extract_detections,  # noqa: E402
                    load_labels, nearness, prepare, rank, zone)
from demo_view import Viewer  # noqa: E402
from speak_detect import summarize  # noqa: E402

W, H = 1280, 720            # the cane's main stream
LW, LH = 640, 360           # the cane's lores stream


def frames(path):
    """(main BGRX 1280x720, lores RGB 640x360), as picamera2 gives them."""
    img = Image.open(path).convert("RGB")
    w, h = img.size
    if w / h > 16 / 9:
        cw = int(h * 16 / 9)
        img = img.crop(((w - cw) // 2, 0, (w - cw) // 2 + cw, h))
    else:
        ch = int(w * 9 / 16)
        img = img.crop((0, (h - ch) // 2, w, (h - ch) // 2 + ch))
    rgb = np.asarray(img.resize((W, H), Image.BILINEAR))
    main = np.dstack([rgb[:, :, 2], rgb[:, :, 1], rgb[:, :, 0],
                      np.full(rgb.shape[:2], 255, np.uint8)])
    lores = np.asarray(img.resize((LW, LH), Image.BILINEAR))
    return main, lores


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("photos", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default=os.path.join(HERE, "models", "smartcane152_v3_h8l.hef"))
    ap.add_argument("--labels", default=os.path.join(HERE, "models", "smartcane152.txt"))
    ap.add_argument("--conf", type=float, default=0.25, help="as the service")
    ap.add_argument("--name-conf", type=float, default=0.35, help="as the service")
    ap.add_argument("--max-objects", type=int, default=2, help="as the service")
    ap.add_argument("--hfov", type=float, default=98.2, help="the cane's camera")
    ap.add_argument("--corridor", type=float, default=15.0)
    args = ap.parse_args()

    from picamera2.devices import Hailo
    labels = load_labels(args.labels)
    os.makedirs(args.out, exist_ok=True)

    def info(d):
        return {"zone": zone(d.x0, d.x1, W, args.hfov, args.corridor),
                "near": nearness(d.y0, d.y1, H),
                "est_m": estimate_m(d, W, H, args.hfov),
                "bearing": bearing(d.x0, d.x1, W, args.hfov)}

    examples = []
    with Hailo(args.model) as hailo:
        in_h, in_w, _ = hailo.get_input_shape()
        inbuf = np.empty((in_h, in_w, 3), dtype=np.uint8)
        # Results are written inside the Hailo block: HailoRT can crash in a
        # native thread when the context closes (8 Oct 2026).
        for path in args.photos:
            name = os.path.splitext(os.path.basename(path))[0]
            main_f, lores = frames(path)
            inp, region = prepare(lores, in_w, in_h, 0, "letterbox", inbuf)
            t0 = time.perf_counter()
            raw = hailo.run(inp)
            infer_ms = 1000 * (time.perf_counter() - t0)
            dets = rank(dedupe(extract_detections(raw, labels, W, H, args.conf, region)),
                        W, H, False)
            v = Viewer(os.path.join(args.out, name + ".jpg"), W, H, args.hfov,
                       args.corridor, info)
            v.write(main_f, dets, 0.0, infer_ms)
            with open(os.path.join(args.out, name + ".json")) as fh:
                vision = json.load(fh)
            # The sentence the cane would speak, by the speech process's own
            # rules: names under --name-conf become "obstacle", no ToF here.
            body = describe(dets, W, H, 3, args.hfov, args.corridor)
            said = summarize(body, set(labels), args.name_conf, None, args.max_objects)
            examples.append({"img": name + ".jpg", "vision": vision, "says": said})
            print(f"{name}: {len(dets)} objects, {infer_ms:.0f} ms, says: {said}")
            for d in vision["dets"]:
                print(f"   {d['label']:<18} {d['score']:.2f} {d['zone']:<5} "
                      f"{'' if d['est_m'] is None else '~%.1f m' % d['est_m']}")
        with open(os.path.join(args.out, "examples.json"), "w") as fh:
            json.dump(examples, fh, indent=1)


if __name__ == "__main__":
    main()
