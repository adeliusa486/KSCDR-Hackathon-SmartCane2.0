#!/usr/bin/env python3
"""Smart cane - run the rest of the data preparation and start training, unattended.

Waits for each download to report success, then, in order:

  1. MTSD: unpack the re-downloaded train.0/train.1, convert to YOLO
  2. Open Images: fetch the 4 classes added after the main fetch started
  3. Roboflow: re-fetch any set that failed (fixed long-name handling)
  4. COCO: arrange into images/ + labels/ layout
  5. build_dataset.py with every source, per-source caps, leakage audit
  6. a per-class check: every class must have boxes, thin classes listed
  7. pseudo_label.py with a COCO and an Open Images teacher (train/val only)
  8. train.py (YOLO11s, 152 classes), in the background of this process

Every stage writes to D:/smartcane-data/pipeline.log. Any failure stops the
pipeline: nothing is trained on data that did not pass its checks.
"""
import json
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
PY = sys.executable
D = Path("D:/smartcane-data")
LOG = D / "pipeline.log"
MERGED = D / "merged_v2"


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def wait_for(path, marker, what, timeout_h=10):
    end = time.time() + timeout_h * 3600
    while time.time() < end:
        p = Path(path)
        if p.exists() and marker in p.read_text(encoding="utf-8", errors="ignore").replace("\0", ""):
            log(f"ready: {what}")
            return
        time.sleep(60)
    fail(f"gave up waiting for {what}")


def fail(msg):
    log(f"STOPPED: {msg}")
    sys.exit(1)


def run(args, what, logfile=None):
    log(f"start: {what}")
    out = open(logfile, "w", encoding="utf-8") if logfile else None
    r = subprocess.run(args, stdout=out or subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0:
        tail = (r.stdout or "")[-1500:] if not out else Path(logfile).read_text(errors="ignore")[-1500:]
        fail(f"{what} exited {r.returncode}: {tail}")
    log(f"done: {what}")
    return r.stdout


def main():
    log("=== overnight pipeline start")
    # 1. MTSD
    wait_for(D / "mtsd_redo.log", "redo done", "MTSD re-download")
    redo = (D / "mtsd_redo.log").read_text()
    if redo.count("OK ") < 2:
        fail(f"MTSD re-download did not verify both files:\n{redo}")
    m = D / "raw/mapillary_mtsd"
    if (D / "mtsd_yolo/data.yaml").exists():
        log("skip: MTSD already converted")
    else:
        for f in ("mtsd_fully_annotated_images.train.0.zip", "mtsd_fully_annotated_images.train.1.zip"):
            log(f"unpack {f}")
            zipfile.ZipFile(m / f).extractall(m)
        run([PY, str(HERE / "convert_mtsd.py"), "--root", str(m), "--out", str(D / "mtsd_yolo")],
            "convert MTSD", D / "mtsd_convert.log")

    # 2. Open Images: main fetch, then the 4 late classes
    wait_for("E:/smartcane-data/oiv7_fetch.log", "fetch exit=0", "Open Images main fetch")
    if Path("E:/smartcane-data/oiv7_extra/dataset.yaml").exists():
        log("skip: Open Images extra classes already fetched")
    else:
        run([PY, str(HERE / "fetch_openimages.py"), "--out", "E:/smartcane-data/oiv7_extra",
             "--labels", "Coffee table,Nightstand,Chest of drawers,Wardrobe"],
            "Open Images extra classes", D / "oiv7_extra_fetch.log")

    # 3. Roboflow: re-fetch failures with the fixed downloader
    wait_for(D / "roboflow_fetch.log", "failed:", "Roboflow downloads")
    reg = yaml.safe_load((HERE / "roboflow_sources.yaml").read_text(encoding="utf-8"))
    for short, v in reg.items():
        ws, proj = v["project"].split("/")
        dest = D / "raw/roboflow" / f"{ws}__{proj}__v{v['version']}"
        n = sum(1 for _ in dest.rglob("*.jpg")) if dest.exists() else 0
        if n == 0 or f"{short}: FAILED" in (D / "roboflow_fetch.log").read_text(errors="ignore").replace("\0", ""):
            if dest.exists():
                shutil.rmtree(dest)
    run([PY, str(HERE / "fetch_all_roboflow.py")], "Roboflow re-fetch", D / "roboflow_refetch.log")
    if "failed: none" not in (D / "roboflow_refetch.log").read_text(errors="ignore"):
        fail("a Roboflow set still fails: " + (D / "roboflow_refetch.log").read_text()[-800:])

    # 4. COCO layout: images/<split> next to labels/<split>
    wait_for(D / "coco_fetch.log", " done", "COCO download")
    c = D / "raw/coco"
    for split in ("train2017", "val2017"):
        src, dst = c / split, c / "coco/images" / split
        # The labels zip leaves empty coco/images/<split> folders behind, so
        # "exists" is not enough: an empty folder must be replaced (3 Oct 2026).
        if dst.exists() and not any(dst.iterdir()):
            dst.rmdir()
        if src.exists() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
        n = sum(1 for _ in dst.glob("*.jpg")) if dst.exists() else 0
        if n == 0:
            fail(f"COCO {split}: no images in {dst}")
        log(f"COCO {split}: {n} images")

    # 5. merge
    wait_for(D / "vistas_convert.log", "exit=0", "Vistas conversion")
    sources = [
        {"name": "coco", "dataset": "coco", "path": str(c / "coco"), "names": "coco",
         "public": True, "max_images": 40000},
        {"name": "oiv7", "dataset": "oiv7", "path": "E:/smartcane-data/oiv7",
         "names_from": "dataset.yaml", "public": True},
        {"name": "oiv7x", "dataset": "oiv7", "path": "E:/smartcane-data/oiv7_extra",
         "names_from": "dataset.yaml", "public": True},
        {"name": "vistas", "dataset": "mapillary", "path": str(D / "vistas_yolo"),
         "names_from": "data.yaml", "public": True},
        {"name": "mtsd", "dataset": "mapillary-mtsd", "path": str(D / "mtsd_yolo"),
         "names_from": "data.yaml", "public": True, "max_images": 30000},
    ]
    for short, v in reg.items():
        ws, proj = v["project"].split("/")
        sources.append({"name": short.replace("rf-", "rf_"), "dataset": short,
                        "path": str(D / "raw/roboflow" / f"{ws}__{proj}__v{v['version']}"),
                        "names_from": "data.yaml", "public": True,
                        "group": r"^(?P<g>.+?)(_(jpe?g|png|bmp|webp))?(\.rf\.[0-9a-f]+)?$",
                        "group_bucket": 50})
    (D / "sources_v2.yaml").write_text(yaml.safe_dump({"sources": sources}, sort_keys=False))
    if MERGED.exists():
        fail(f"{MERGED} already exists, refusing to overwrite evidence")
    run([PY, str(HERE / "build_dataset.py"), "--sources", str(D / "sources_v2.yaml"),
         "--out", str(MERGED), "--classes", str(HERE / "classes_v2.yaml"), "--copy"],
        "build merged dataset", D / "build_v2.log")

    # 6. every class must have data
    audit = json.loads((MERGED / "audit.json").read_text())
    names = [x["name"] for x in yaml.safe_load((HERE / "classes_v2.yaml").read_text())["classes"]]
    train = audit["per_split"].get("train", {})
    empty = [n for n in names if train.get(n, 0) == 0]
    thin = sorted(((train.get(n, 0), n) for n in names if 0 < train.get(n, 0) < 300))
    log(f"train images {train.get('_images')}, classes with no boxes: {empty}")
    log(f"thin classes (< 300 boxes): {thin}")
    if audit["leaking_groups"]:
        fail(f"leakage: {len(audit['leaking_groups'])} groups in two splits")
    if empty:
        fail("classes with no training boxes, not training: " + ", ".join(empty))

    # 7. fill unlabelled objects
    run([PY, str(HERE / "pseudo_label.py"), "--data", str(MERGED),
         "--teacher", "coco=yolo11m.pt", "--teacher", "oiv7=yolov8m-oiv7.pt"],
        "pseudo-label train/val", D / "pseudo_v2.log")

    # 8. train
    run([PY, str(HERE / "train.py"), "--data", str(MERGED / "smartcane.yaml"),
         "--model", "yolo11s.pt", "--epochs", "40", "--batch", "12", "--name", "smartcane152_v2"],
        "train YOLO11s, 152 classes, 40 epochs", D / "train_v2.log")
    log("=== pipeline finished: model trained")


if __name__ == "__main__":
    main()
