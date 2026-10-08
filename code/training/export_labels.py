#!/usr/bin/env python3
"""Smart cane - pack the training set's labels for the public repository.

The images (88 GB for merged_v2) cannot go into git: GitHub refuses files
over 100 MB and repositories are meant to stay under a few GB. Everything
else does fit: every YOLO label file, the human labels before
pseudo-labelling, the pseudo-label and cleaning logs, and per-class and
per-source counts. Image file names carry their source and original ID
(coco__train2017__000000000042.jpg), so with docs/training.md anyone can
fetch the same images from the original datasets and drop them next to
these labels.

Reads run on 32 threads. On this laptop one small file took ~17 ms to open
(56 files/s, real-time scanning), 32 threads read 884 files/s.

    python export_labels.py --data "D:/smart cane 2.0/datasets/merged_v2" \
        --out data/merged_v2 --names models/smartcane152_v3/smartcane152.txt
"""
import argparse
import collections
import csv
import io
import json
import os
import tarfile
import zipfile
from concurrent.futures import ThreadPoolExecutor

MAX_ZIP = 95 * 1024 * 1024      # GitHub refuses files over 100 MB


def source_of(name):
    """'coco__train2017__000000000042.txt' -> 'coco'."""
    return name.split("__", 1)[0] if "__" in name else "other"


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


def pack(src, zpath, arc_prefix, counts, images, sources, key, split):
    """Pack every .txt in src into one solid .tar.xz and count boxes per
    class from the same bytes. Solid compression matters: a zip compresses
    each 300-byte label on its own and came out at 81 MB for 87 MB of text.
    Returns (files, bytes in)."""
    names = sorted(e.name for e in os.scandir(src) if e.name.endswith(".txt"))
    n = size = 0
    with tarfile.open(zpath, "w:xz", preset=9) as z, ThreadPoolExecutor(32) as ex:
        for name, data in zip(names, ex.map(read, (os.path.join(src, x) for x in names))):
            info = tarfile.TarInfo(f"{arc_prefix}/{name}")
            info.size = len(data)
            info.mtime = 0
            z.addfile(info, io.BytesIO(data))
            n += 1
            size += len(data)
            if sources is not None:
                sources[(split, source_of(name))] += 1
            seen = set()
            for line in data.decode().splitlines():
                parts = line.split()
                if parts:
                    c = int(parts[0])
                    counts[(key, split, c)] += 1
                    seen.add(c)
            for c in seen:
                images[(key, split, c)] += 1
            if n % 20000 == 0:
                print(f"  {arc_prefix}: {n}/{len(names)}", flush=True)
    if os.path.getsize(zpath) > MAX_ZIP:
        raise SystemExit(f"{zpath} is over 95 MB, split it before committing")
    return n, size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="merged_v2 folder")
    ap.add_argument("--out", required=True)
    ap.add_argument("--names", required=True, help="class names, one per line")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    names = [l.strip() for l in open(args.names) if l.strip()]

    counts = collections.Counter()
    images = collections.Counter()
    sources = collections.Counter()
    report = {}
    for split in ("train", "val"):
        for kind, folder, key in (("labels", "labels", "final"),
                                  ("labels_human", "labels_human", "human")):
            src = os.path.join(args.data, folder, split)
            if not os.path.isdir(src):
                continue
            z = os.path.join(args.out, f"{kind}_{split}.tar.xz")
            n, size = pack(src, z, f"{folder}/{split}", counts, images,
                           sources if key == "final" else None, key, split)
            report[f"{kind}_{split}"] = {"files": n, "bytes": size,
                                         "zip_bytes": os.path.getsize(z)}
            print(f"{z}: {n} files, {size / 1e6:.1f} MB -> "
                  f"{os.path.getsize(z) / 1e6:.1f} MB", flush=True)

    with zipfile.ZipFile(os.path.join(args.out, "pseudo_labels.csv.zip"), "w",
                         zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.write(os.path.join(args.data, "pseudo_labels.csv"), "pseudo_labels.csv")
    for f in ("pseudo_removed.csv", "mtsd_stop_relabel.csv", "audit.json"):
        p = os.path.join(args.data, f)
        if os.path.exists(p):
            with open(p, "rb") as a, open(os.path.join(args.out, f), "wb") as b:
                b.write(a.read())

    with open(os.path.join(args.out, "class_counts.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "class", "train_boxes", "train_images", "val_boxes",
                    "val_images", "train_boxes_human", "train_boxes_pseudo"])
        for i, n in enumerate(names):
            tb, hb = counts[("final", "train", i)], counts[("human", "train", i)]
            w.writerow([i, n, tb, images[("final", "train", i)],
                        counts[("final", "val", i)], images[("final", "val", i)],
                        hb, tb - hb])
    with open(os.path.join(args.out, "source_counts.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["split", "source", "images"])
        for (split, src), n in sorted(sources.items()):
            w.writerow([split, src, n])

    # Dataset descriptor with a relative path, so it works wherever the
    # images are put.
    with open(os.path.join(args.out, "smartcane.yaml"), "w") as fh:
        fh.write("# Ultralytics dataset descriptor for merged_v2. Put images/ and the\n"
                 "# unzipped labels/ next to this file.\n")
        fh.write("path: .\ntrain: images/train\nval: images/val\nnames:\n")
        for i, n in enumerate(names):
            fh.write(f"  {i}: {n}\n")
    report["sources"] = {f"{s}/{src}": n for (s, src), n in sorted(sources.items())}
    with open(os.path.join(args.out, "export_report.json"), "w") as fh:
        json.dump(report, fh, indent=1)
    print("done", flush=True)


if __name__ == "__main__":
    main()
