#!/usr/bin/env python3
"""Smart cane - build one merged YOLO dataset from many public sources.

The hard part of this job is not downloading. It is that every dataset uses a
different label scheme, a different file layout and a different annotation
format, and they all disagree about what a "pothole" is called. This script
normalises them onto the single class list in classes.yaml.

Run it from anywhere:

    python prepare_datasets.py --out C:/ml/smartcane/data --check
    python prepare_datasets.py --out C:/ml/smartcane/data --fetch coco,roboflow

Use --check first. It tells you exactly which datasets are ready, which need a
free API key, and which you have to download by hand, without touching the
network.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
CLASSES_YAML = HERE / "classes.yaml"

# COCO's 80 classes in their canonical order. Index 0 must stay "person" so
# pretrained weights transfer without remapping.
COCO = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag",
    "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon",
    "bowl", "banana", "apple", "sandwich", "orange", "broccoli", "carrot",
    "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant",
    "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
]

# How each source dataset names the things we care about. Everything on the
# left becomes the class on the right. Lowercased before lookup.
LABEL_ALIASES = {
    # pothole
    "pothole": "pothole", "potholes": "pothole", "d40": "pothole",
    "pot hole": "pothole", "road-pothole": "pothole",
    # manhole
    "manhole": "manhole", "manhole cover": "manhole", "sewer cover": "manhole",
    "sewer": "manhole", "drain cover": "manhole",
    # open drain
    "open drain": "open drain", "open-drain": "open drain",
    "open manhole": "open drain", "uncovered drain": "open drain",
    # stairs
    "stairs": "stairs", "stair": "stairs", "staircase": "stairs",
    "steps": "stairs",
    # curb
    "curb": "curb", "kerb": "curb", "curbstone": "curb", "sidewalk edge": "curb",
    # pole
    "pole": "pole", "poles": "pole", "street pole": "pole",
    "utility pole": "pole", "scaffolding pole": "pole",
    # scaffolding
    "scaffolding": "scaffolding", "sidewalk shed": "scaffolding",
    "horizontal scaffolding": "scaffolding",
    # door
    "door": "door", "doors": "door", "doorway": "door",
    # Obstacle-Dataset OD uses underscored names. Its motorbike maps onto
    # COCO's motorcycle rather than becoming a new class.
    "reflective_cone": "traffic cone", "traffic_cone": "traffic cone",
    "cone": "traffic cone",
    "warning_column": "bollard", "bollard": "bollard",
    "ashcan": "trash bin", "trash_bin": "trash bin", "dustbin": "trash bin",
    "spherical_roadblock": "roadblock", "roadblock": "roadblock",
    "tricycle": "tricycle", "rickshaw": "tricycle", "auto_rickshaw": "tricycle",
    "motorbike": "motorcycle",
    "stop_sign": "stop sign", "fire_hydrant": "fire hydrant",
}


def load_classes():
    cfg = yaml.safe_load(CLASSES_YAML.read_text())
    names = list(COCO)
    for entry in cfg["added_classes"]:
        if entry["index"] != len(names):
            sys.exit(f"classes.yaml index gap at {entry['name']}: expected "
                     f"{len(names)}, got {entry['index']}")
        names.append(entry["name"])
    return cfg, names


def have(cmd):
    return shutil.which(cmd) is not None


def check(cfg, names):
    print(f"class list: {len(names)} classes "
          f"({cfg['base_class_count']} COCO + {len(cfg['added_classes'])} added)")
    print()
    key = os.environ.get("ROBOFLOW_API_KEY")
    ready, needs_key, manual = [], [], []
    for name, d in cfg["datasets"].items():
        auth = d.get("auth", "manual")
        if auth == "none":
            ready.append(name)
        elif auth == "key":
            (ready if key else needs_key).append(name)
        else:
            manual.append(name)

    print("READY TO FETCH AUTOMATICALLY")
    for n in ready:
        print(f"  + {n}")
    if needs_key:
        print("\nNEEDS A FREE ROBOFLOW API KEY")
        print("  get one at roboflow.com, then:")
        print("    setx ROBOFLOW_API_KEY \"your_key_here\"   (reopen the shell)")
        for n in needs_key:
            print(f"  - {n}  {cfg['datasets'][n].get('url','')}")
    if manual:
        print("\nDOWNLOAD BY HAND (no public direct link, or licence gate)")
        for n in manual:
            d = cfg["datasets"][n]
            print(f"  - {n}")
            print(f"      {d.get('url', 'see classes.yaml')}")
            print(f"      put the extracted folder in: <out>/raw/{n}/")
    print()
    print("tools:")
    for t in ("git", "unzip"):
        print(f"  {'+' if have(t) else '-'} {t}")


def fetch_git(url, dest):
    if dest.exists():
        print(f"  already present: {dest}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  git clone {url}")
    subprocess.run(["git", "clone", "--depth", "1", url, str(dest)], check=True)


def fetch_roboflow(cfg, key, out):
    try:
        from roboflow import Roboflow
    except ImportError:
        sys.exit("pip install roboflow")
    rf = Roboflow(api_key=key)
    for name, d in cfg["datasets"].items():
        if d.get("auth") != "key":
            continue
        url = d.get("url", "")
        parts = url.rstrip("/").split("/")
        if len(parts) < 2:
            print(f"  skip {name}: cannot parse url")
            continue
        workspace, project = parts[-2], parts[-1]
        dest = out / "raw" / name
        if dest.exists():
            print(f"  already present: {name}")
            continue
        print(f"  downloading {name} from roboflow ...")
        try:
            proj = rf.workspace(workspace).project(project)
            version = proj.versions()[0]
            version.download("yolov8", location=str(dest))
        except Exception as e:
            print(f"  FAILED {name}: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="dataset root, e.g. C:/ml/smartcane/data")
    ap.add_argument("--check", action="store_true",
                    help="report what is available, touch nothing")
    ap.add_argument("--fetch", default="",
                    help="comma list: coco,roboflow,git  (or 'all')")
    args = ap.parse_args()

    cfg, names = load_classes()
    out = Path(args.out)

    if args.check or not args.fetch:
        check(cfg, names)
        if not args.fetch:
            print("nothing fetched. pass --fetch to download.")
        return

    out.mkdir(parents=True, exist_ok=True)
    want = {w.strip() for w in args.fetch.split(",")}
    if "all" in want:
        want = {"coco", "roboflow", "git"}

    if "git" in want:
        print("git sources:")
        for name, d in cfg["datasets"].items():
            u = d.get("url", "")
            if d.get("auth") == "none" and u.endswith(".git"):
                fetch_git(u, out / "raw" / name)

    if "roboflow" in want:
        key = os.environ.get("ROBOFLOW_API_KEY")
        if not key:
            print("roboflow: ROBOFLOW_API_KEY not set, skipping")
        else:
            print("roboflow sources:")
            fetch_roboflow(cfg, key, out)

    if "coco" in want:
        print("coco: Ultralytics downloads it on first train, nothing to do here.")

    # Write the merged dataset descriptor Ultralytics will train against.
    yolo_yaml = out / "smartcane.yaml"
    yolo_yaml.write_text(yaml.safe_dump({
        "path": str(out).replace("\\", "/"),
        "train": "images/train",
        "val": "images/val",
        "names": {i: n for i, n in enumerate(names)},
    }, sort_keys=False))
    print(f"\nwrote {yolo_yaml}  ({len(names)} classes)")


if __name__ == "__main__":
    main()
