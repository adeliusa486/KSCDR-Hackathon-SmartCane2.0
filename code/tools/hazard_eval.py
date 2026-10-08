#!/usr/bin/env python3
"""Smart cane - run real labelled photos through the Hailo, per safety class.

The closest thing to walking the cane past every hazard without leaving the
room. Each photo goes through the same path as the camera's lores frame
(plain resize to the model input, RGB) and the same decoder as detect.py.

For each labelled object it asks two questions, the two that matter to a
blind user:
  named:    was it detected with the RIGHT name at the naming threshold?
  noticed:  was ANYTHING detected on it at the detection threshold? The cane
            says "obstacle" for those, so the user is still warned.

    python3 tools/hazard_eval.py --model models/smartcane152_v3_h8l.hef \
        --labels smartcane152.txt --images ~/hazard_eval
"""
import argparse
import glob
import json
import os
import sys
import time

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from detect import dedupe, extract_detections, load_labels, prepare  # noqa: E402


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def crop_169(img, boxes):
    """Centre-crop to 16:9 like the camera frame. boxes: normalised
    (x0, y0, x1, y1). Boxes less than half inside the crop are dropped."""
    w, h = img.size
    if w / h > 16 / 9:
        cw, ch = int(h * 16 / 9), h
    else:
        cw, ch = w, int(w * 9 / 16)
    ox, oy = (w - cw) // 2, (h - ch) // 2
    img = img.crop((ox, oy, ox + cw, oy + ch))
    out = []
    for name, (x0, y0, x1, y1) in boxes:
        a = (x0 * w, y0 * h, x1 * w, y1 * h)
        b = (max(a[0], ox), max(a[1], oy), min(a[2], ox + cw), min(a[3], oy + ch))
        if b[2] <= b[0] or b[3] <= b[1]:
            continue
        if (b[2] - b[0]) * (b[3] - b[1]) < 0.5 * (a[2] - a[0]) * (a[3] - a[1]):
            continue
        out.append((name, ((b[0] - ox) / cw, (b[1] - oy) / ch,
                           (b[2] - ox) / cw, (b[3] - oy) / ch)))
    return img, out


def tilt(img, boxes, deg):
    """Turn the photo deg clockwise, boxes with it."""
    if not deg:
        return img, boxes
    img = img.transpose({90: Image.Transpose.ROTATE_270,
                         180: Image.Transpose.ROTATE_180,
                         270: Image.Transpose.ROTATE_90}[deg])
    turn = {90: lambda x0, y0, x1, y1: (1 - y1, x0, 1 - y0, x1),
            180: lambda x0, y0, x1, y1: (1 - x1, 1 - y1, 1 - x0, 1 - y0),
            270: lambda x0, y0, x1, y1: (y0, 1 - x1, y1, 1 - x0)}[deg]
    return img, [(n, turn(*b)) for n, b in boxes]


def report(args, stats, times, files):
    """Print and save the results. Called INSIDE the Hailo block: on 8 Oct
    2026 HailoRT segfaulted in a native thread every time the Hailo context
    closed, and results written after that were lost."""
    tot = {k: sum(s[k] for s in stats.values()) for k in ("objects", "named", "noticed")}
    median_ms = 1000 * sorted(times)[len(times) // 2]
    if args.json:
        with open(args.json, "w") as fh:
            json.dump({"config": vars(args), "stats": stats, "total": tot,
                       "median_ms": median_ms}, fh, indent=1)
    n = max(1, tot["objects"])
    print(f"aspect {args.aspect}, fit {args.fit}, order {args.order}, tilt {args.tilt}")
    print(f"{len(files)} photos, Hailo inference median {median_ms:.1f} ms")
    print(f"{'ALL':22s} {tot['objects']:5d} {100 * tot['named'] / n:6.0f}% "
          f"{100 * tot['noticed'] / n:7.0f}%", flush=True)
    print()
    print(f"{'object':22s} {'count':>5s} {'named':>7s} {'noticed':>8s}")
    for c in sorted(stats, key=lambda c: -stats[c]["noticed"] / max(1, stats[c]["objects"])):
        s = stats[c]
        n = max(1, s["objects"])
        print(f"{c:22s} {s['objects']:5d} {100 * s['named'] / n:6.0f}% {100 * s['noticed'] / n:7.0f}%")
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--images", required=True)
    ap.add_argument("--conf", type=float, default=0.25, help="detection threshold (service)")
    ap.add_argument("--name-conf", type=float, default=0.35, help="naming threshold (service)")
    ap.add_argument("--iou", type=float, default=0.3)
    ap.add_argument("--min-size", type=float, default=0.02,
                    help="ignore labelled objects smaller than this fraction of "
                         "the frame height: too far away to matter to a walker")
    ap.add_argument("--json", help="write per-class results here")
    ap.add_argument("--aspect", choices=("photo", "16:9"), default="photo")
    ap.add_argument("--fit", choices=("stretch", "letterbox"), default="stretch")
    ap.add_argument("--order", choices=("rgb", "bgr"), default="rgb")
    ap.add_argument("--tilt", type=int, choices=(0, 90, 180, 270), default=0)
    args = ap.parse_args()

    from picamera2.devices import Hailo
    labels = load_labels(args.labels)
    index = json.load(open(os.path.join(args.images, "_index.json")))
    want = set(index["per_class"])

    stats = {c: {"objects": 0, "named": 0, "noticed": 0} for c in want}
    times = []
    files = sorted(f for f in glob.glob(os.path.join(args.images, "*"))
                   if f.lower().endswith((".jpg", ".jpeg", ".png")))
    with Hailo(args.model) as hailo:
        h, w, _ = hailo.get_input_shape()
        inbuf = np.empty((h, w, 3), dtype=np.uint8)   # one buffer, see prepare()
        for f in files:
            img = Image.open(f).convert("RGB")
            gt_path = os.path.splitext(f)[0] + ".txt"
            boxes = []
            for row in open(gt_path).read().splitlines():
                if not row.strip():
                    continue
                c, cx, cy, bw, bh = row.split()[:5]
                cx, cy, bw, bh = map(float, (cx, cy, bw, bh))
                boxes.append((labels[int(c)],
                              (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)))
            if args.aspect == "16:9":
                img, boxes = crop_169(img, boxes)
            img, boxes = tilt(img, boxes, args.tilt)
            arr = np.array(img)
            if args.order == "bgr":
                arr = np.ascontiguousarray(arr[:, :, ::-1])
            inp, region = prepare(arr, w, h, 0, args.fit, inbuf)
            t0 = time.perf_counter()
            raw = hailo.run(inp)
            times.append(time.perf_counter() - t0)
            dets = dedupe(extract_detections(raw, labels, 1.0, 1.0, args.conf, region))
            for name, box in boxes:
                # Size is judged in the upright world, so a tilted photo keeps
                # the same set of objects.
                size = (box[2] - box[0]) if args.tilt in (90, 270) else (box[3] - box[1])
                if name not in want or size < args.min_size:
                    continue
                s = stats[name]
                s["objects"] += 1
                hits = [d for d in dets if iou(box, (d.x0, d.y0, d.x1, d.y1)) >= args.iou]
                if hits:
                    s["noticed"] += 1
                if any(d.label == name and d.score >= args.name_conf for d in hits):
                    s["named"] += 1
        report(args, stats, times, files)


if __name__ == "__main__":
    main()
