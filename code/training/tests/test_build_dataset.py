#!/usr/bin/env python3
"""Test build_dataset.py on synthetic sources with planted problems.

    C:/ml/venv/Scripts/python.exe code/training/tests/test_build_dataset.py

Planted: video frames that must stay together, an image duplicated across
sources, a corrupt file, an unknown class, an out-of-range box, a missing
label, a video source with no group regex, and private sessions that are the
only thing allowed into test.
"""
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from PIL import Image

HERE = Path(__file__).resolve().parent
BUILD = HERE.parent / "build_dataset.py"
failures = 0


def check(cond, msg):
    global failures
    if not cond:
        failures += 1
        print(f"FAIL: {msg}")


def smooth_image(seed, offset=0):
    """Smooth 64x64 image from a random 4x4 grid. A uniform brightness
    offset leaves its difference hash unchanged, like neighbouring video
    frames; a different seed gives an unrelated image."""
    rnd = random.Random(seed)
    small = Image.new("RGB", (4, 4))
    small.putdata([tuple(rnd.randrange(30, 220) for _ in range(3)) for _ in range(16)])
    img = small.resize((64, 64), Image.BILINEAR)
    return img.point(lambda v: min(255, v + offset))


def write(root, rel, img, label):
    p = root / "images" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    img.save(p, quality=95)
    if label is not None:
        lp = (root / "labels" / rel).with_suffix(".txt")
        lp.parent.mkdir(parents=True, exist_ok=True)
        lp.write_text(label)


def build(tmp):
    src = tmp / "src"
    # Public dashcam: 3 videos x 8 frames, classes named the source's way.
    for v in range(3):
        for f in range(8):
            write(src / "dashcam", f"train/vid{v}_frame{f:04d}.jpg",
                  smooth_image(100 + v, offset=f), "0 0.5 0.5 0.2 0.2\n1 0.3 0.3 0.1 0.1\n")
    # Public stills: independent photos plus planted problems.
    for i in range(30):
        write(src / "stills", f"img_{i}.jpg", smooth_image(1000 + i), "0 0.5 0.5 0.3 0.3\n")
    write(src / "stills", "copy_of_vid1.jpg", smooth_image(101, offset=3), "0 0.5 0.5 0.3 0.3\n")
    write(src / "stills", "graffiti.jpg", smooth_image(2001), "1 0.5 0.5 0.3 0.3\n")
    write(src / "stills", "badbox.jpg", smooth_image(2002), "0 1.7 0.5 0.3 0.3\n")
    write(src / "stills", "nolabel.jpg", smooth_image(2003), None)
    # Roboflow polygon export: an outline instead of a box
    write(src / "stills", "polygon.jpg", smooth_image(2004), "0 0.4 0.4 0.6 0.4 0.6 0.6 0.4 0.6\n")
    (src / "stills" / "images" / "corrupt.jpg").write_bytes(b"not a jpeg at all")
    # Public video with no group regex: a dark object moving across a fixed
    # scene. Neighbours differ by more than a near duplicate but still look
    # alike. Must trigger the video warning.
    for f in range(6):
        frame = smooth_image(3000)
        frame.paste((10, 10, 10), (8 * f, 20, 8 * f + 14, 34))
        write(src / "clips", f"clipX_frame{f:04d}.jpg", frame, "0 0.5 0.5 0.2 0.2\n")
    # Private cane sessions: the only data allowed into test.
    for s in range(12):
        for k in range(3):
            write(src / "cane", f"sess{s:02d}_{k}.jpg", smooth_image(5000 + 10 * s + k), "0 0.5 0.5 0.2 0.2\n")

    cfg = {"sources": [
        {"name": "dashcam", "path": str(src / "dashcam"), "names": ["potholes", "car"],
         "group": r"^(?P<g>.+)_frame\d+$", "public": True},
        {"name": "stills", "path": str(src / "stills"), "names": ["person", "graffiti"],
         "public": True},
        {"name": "clips", "path": str(src / "clips"), "names": ["person"], "public": True},
        {"name": "cane", "path": str(src / "cane"), "names": ["kerb"],
         "group": r"^(?P<g>sess\d+)_", "public": False},
    ]}
    (tmp / "sources.yaml").write_text(yaml.safe_dump(cfg))


def run(tmp, out):
    return subprocess.run([sys.executable, str(BUILD), "--sources", str(tmp / "sources.yaml"),
                           "--out", str(out), "--split", "0.6,0.2,0.2", "--copy"],
                          capture_output=True, text=True)


with tempfile.TemporaryDirectory() as t:
    tmp = Path(t)
    build(tmp)
    res = run(tmp, tmp / "out")
    print(res.stdout.strip())
    check(res.returncode == 0, f"build exit {res.returncode}: {res.stderr[-400:]}")
    audit = json.loads((tmp / "out" / "audit.json").read_text())
    names = yaml.safe_load((tmp / "out" / "smartcane.yaml").read_text())["names"]
    idx = {v: k for k, v in names.items()}

    def split_files(split):
        d = tmp / "out" / "images" / split
        return [p.name for p in d.iterdir()] if d.exists() else []

    where = {f: s for s in ("train", "val", "test") for f in split_files(s)}
    check(audit["leaking_groups"] == [], "no group in two splits")
    for v in range(3):
        splits = {s for f, s in where.items() if f.startswith(f"dashcam__train__vid{v}_")}
        check(len(splits) == 1, f"all frames of vid{v} in one split ({splits})")
    check(where.get("stills__copy_of_vid1.jpg") == where.get("dashcam__train__vid1_frame0000.jpg"),
          "cross-source duplicate shares its video's split")
    check(all(f.startswith("cane__") for f in split_files("test")), "test holds cane data only")
    check(len(split_files("test")) > 0, "some cane sessions reach test")
    sess = {}
    for f, s in where.items():
        if f.startswith("cane__"):
            sess.setdefault(f.split("_")[2], set()).add(s)
    check(all(len(v) == 1 for v in sess.values()), "each cane session in one split")

    lbl = (tmp / "out" / "labels" / where["dashcam__train__vid0_frame0000.jpg"] /
           "dashcam__train__vid0_frame0000.txt").read_text().split()
    check(lbl[0] == str(idx["pothole"]) and lbl[5] == str(idx["car"]),
          f"'potholes' -> pothole ({idx['pothole']}), 'car' -> car ({idx['car']})")
    check(audit["dropped_classes"].get("stills:graffiti") == 1, "unknown class dropped and counted")
    check(any("corrupt.jpg" in c for c in audit["corrupt_images"]), "corrupt image reported")
    check(any("badbox.jpg" in b for b in audit["bad_label_lines"]), "out-of-range box reported")
    check(audit["missing_labels"].get("stills") == 1, "missing label counted")
    check(any("clips" in w for w in audit["video_frame_warnings"]), "video without group regex warned")
    check(not any("stills" in w for w in audit["video_frame_warnings"]), "no false video warning on stills")
    check(audit["near_duplicates"] > 0, "near duplicates found")
    poly = (tmp / "out" / "labels" / where["stills__polygon.jpg"] / "stills__polygon.txt").read_text().split()
    check(poly[0] == str(idx["person"]) and [round(float(v), 4) for v in poly[1:]] == [0.5, 0.5, 0.2, 0.2],
          f"polygon label becomes its bounding box ({poly})")
    check(audit["polygons_converted"] == 1, "polygon conversion counted")

    again = run(tmp, tmp / "out")
    check(again.returncode != 0, "refuses to overwrite an existing build")
    run(tmp, tmp / "out2")
    where2 = {f: s for s in ("train", "val", "test")
              for f in ([p.name for p in (tmp / "out2" / "images" / s).iterdir()]
                        if (tmp / "out2" / "images" / s).exists() else [])}
    check(where == where2, "same input, same split")

if failures:
    print(f"{failures} check(s) failed")
    sys.exit(1)
print("all build_dataset checks passed")
