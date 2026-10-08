#!/usr/bin/env python3
"""Smart cane - record the live dashboard for replay.

A venue's Wi-Fi can fail during a demo. Record a real session beforehand and
the dashboard (and the project website) plays it back exactly as it was:
the frames with their boxes, the detections, the ToF and ground readings and
everything the cane said.

Needs the dashboard running (speak_detect.py --demo-port 8080). Point the
cane at a scene with things in it, then:

    python3 tools/record_demo.py --seconds 30 --out ~/replay
    python3 tools/record_demo.py --url http://smartcane.local:8080 --token T --out replay

Copy the folder to web/replay/ of the repository to put it on the website.
Writes replay.json and fNNNN.jpg files, about 30 KB per frame at --width 640.
"""
import argparse
import io
import json
import os
import time
import urllib.parse
import urllib.request


def get(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--token", default="")
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--rate", type=float, default=5.0, help="samples per second")
    ap.add_argument("--width", type=int, default=640, help="frame width to store, 0 = as is")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    q = "?token=" + urllib.parse.quote(args.token) if args.token else ""
    os.makedirs(args.out, exist_ok=True)
    frames, last_frame, t0 = [], None, time.time()
    try:
        from PIL import Image
    except ImportError:
        Image = None
    while time.time() - t0 < args.seconds:
        tick = time.time()
        try:
            state = json.loads(get(args.url + "/state.json" + q))
            fid = (state.get("vision") or {}).get("frame")
            if fid is not None and fid != last_frame:
                jpg = get(args.url + "/frame.jpg" + q)
                if Image is not None and args.width:
                    im = Image.open(io.BytesIO(jpg)).convert("RGB")
                    if im.width > args.width:
                        im = im.resize((args.width, round(im.height * args.width / im.width)),
                                       Image.BILINEAR)
                    buf = io.BytesIO()
                    im.save(buf, "JPEG", quality=70)
                    jpg = buf.getvalue()
                name = f"f{len(frames) + 1:04d}.jpg"
                with open(os.path.join(args.out, name), "wb") as fh:
                    fh.write(jpg)
                frames.append({"t": round(tick - t0, 2), "img": name, "state": state})
                last_frame = fid
        except (OSError, ValueError) as e:
            print(f"  skip: {e}")
        time.sleep(max(0.0, 1.0 / args.rate - (time.time() - tick)))
    meta = {"recorded": time.strftime("%Y-%m-%dT%H:%M:%S"), "seconds": args.seconds,
            "frames": frames}
    if frames:
        meta["model"] = frames[0]["state"].get("model")
        meta["classes"] = frames[0]["state"].get("classes")
    with open(os.path.join(args.out, "replay.json"), "w") as fh:
        json.dump(meta, fh)
    size = sum(os.path.getsize(os.path.join(args.out, f["img"])) for f in frames)
    print(f"{len(frames)} frames, {size / 1e6:.1f} MB in {args.out}")


if __name__ == "__main__":
    main()
