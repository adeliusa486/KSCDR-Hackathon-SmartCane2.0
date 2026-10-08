#!/usr/bin/env python3
"""Smart cane - inspect and download Roboflow Universe datasets in YOLO format.

Needs the API key in the ROBOFLOW_API_KEY environment variable (never in a
file). Inspect first, then download only what the class list needs:

    python roboflow_fetch.py --inspect ws/project ws/project2 ...
    python roboflow_fetch.py --download ws/project[:version] ... --out "D:/smart cane 2.0/datasets/raw/roboflow"

--inspect prints, per project: latest version, image count, class names and
their counts, licence. The download writes <out>/<ws>__<project>/ in YOLOv8
layout (train/valid/test folders with images/ and labels/, plus data.yaml).
"""
import argparse
import hashlib
import io
import json
import os
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

API = "https://api.roboflow.com"


def get(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.loads(r.read().decode())


def key():
    k = os.environ.get("ROBOFLOW_API_KEY")
    if not k:
        sys.exit("ROBOFLOW_API_KEY is not set")
    return k


def inspect(slug):
    ws, proj = slug.split("/")[:2]
    try:
        d = get(f"{API}/{ws}/{proj}?api_key={key()}")
    except Exception as e:
        return {"slug": slug, "error": str(e)}
    p = d.get("project", {})
    versions = d.get("versions", [])
    latest = max((int(v["id"].split("/")[-1]) for v in versions), default=None)
    return {"slug": slug, "images": p.get("images"), "classes": p.get("classes"),
            "versions": len(versions), "latest": latest, "license": p.get("license"),
            "type": p.get("type")}


def short_name(member, limit=120):
    """Windows refuses paths over 260 characters, and some Roboflow file
    names are longer than that on their own (obstacles-for-blind v5). Hash
    an over-long original-photo part, keep the '_jpg.rf.<hash>' ending so
    dedupe_roboflow.py still groups the copies, and do the same to the
    matching label (same stem, same hash)."""
    p = Path(member)
    if len(p.name) <= limit:
        return p
    stem, suffix = p.stem, p.suffix
    orig, sep, rest = stem.partition(".rf.")
    short = hashlib.sha1(orig.encode()).hexdigest()[:20]
    return p.with_name(f"{short}{sep}{rest}{suffix}")


def download(slug, out):
    ws, proj = slug.split("/")[:2]
    ver = slug.split(":")[1] if ":" in slug else None
    proj = proj.split(":")[0]
    if ver is None:
        ver = inspect(f"{ws}/{proj}")["latest"]
    # Roboflow builds an export on first request. Until it is ready the reply
    # has no "export" link (labelimg underground v1 on 3 Oct), so ask again.
    for attempt in range(20):
        d = get(f"{API}/{ws}/{proj}/{ver}/yolov8?api_key={key()}")
        if "export" in d:
            break
        time.sleep(30)
    else:
        raise RuntimeError(f"no export link after 10 min: {str(d)[:200]}")
    link = d["export"]["link"]
    dest = Path(out) / f"{ws}__{proj}__v{ver}"
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(link, timeout=600) as r:
                z = zipfile.ZipFile(io.BytesIO(r.read()))
            break
        except (OSError, zipfile.BadZipFile) as e:   # connection reset, truncated zip
            if attempt == 3:
                raise
            print(f"{slug}: download attempt {attempt} failed ({e}), retrying", flush=True)
            time.sleep(30 * attempt)
    for m in z.infolist():
        if m.is_dir():
            continue
        target = dest / short_name(m.filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(z.read(m))
    n = sum(1 for _ in dest.rglob("*.jpg")) + sum(1 for _ in dest.rglob("*.png"))
    print(f"{slug} v{ver}: {n} images -> {dest}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inspect", nargs="*", default=[])
    ap.add_argument("--download", nargs="*", default=[])
    ap.add_argument("--out", default="D:/smart cane 2.0/datasets/raw/roboflow")
    args = ap.parse_args()
    for s in args.inspect:
        r = inspect(s)
        if "error" in r:
            print(f"{s}: ERROR {r['error']}")
            continue
        top = sorted((r["classes"] or {}).items(), key=lambda kv: -kv[1])[:14]
        print(f"{s}: {r['images']} images, type {r['type']}, v{r['latest']}, licence {r['license']}")
        print(f"    {top}")
    failed = []
    for s in args.download:
        try:
            download(s, args.out)
        except Exception as e:          # one bad project must not stop the rest
            print(f"{s}: FAILED {type(e).__name__}: {e}", flush=True)
            failed.append(s)
    if failed:
        print(f"{len(failed)} failed: {failed}")
        sys.exit(1)


if __name__ == "__main__":
    main()
