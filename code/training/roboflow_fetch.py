#!/usr/bin/env python3
"""Smart cane - inspect and download Roboflow Universe datasets in YOLO format.

Needs the API key in the ROBOFLOW_API_KEY environment variable (never in a
file). Inspect first, then download only what the class list needs:

    python roboflow_fetch.py --inspect ws/project ws/project2 ...
    python roboflow_fetch.py --download ws/project[:version] ... --out D:/smartcane-data/raw/roboflow

--inspect prints, per project: latest version, image count, class names and
their counts, licence. The download writes <out>/<ws>__<project>/ in YOLOv8
layout (train/valid/test folders with images/ and labels/, plus data.yaml).
"""
import argparse
import io
import json
import os
import sys
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


def download(slug, out):
    ws, proj = slug.split("/")[:2]
    ver = slug.split(":")[1] if ":" in slug else None
    proj = proj.split(":")[0]
    if ver is None:
        ver = inspect(f"{ws}/{proj}")["latest"]
    d = get(f"{API}/{ws}/{proj}/{ver}/yolov8?api_key={key()}")
    link = d["export"]["link"]
    dest = Path(out) / f"{ws}__{proj}__v{ver}"
    with urllib.request.urlopen(link, timeout=600) as r:
        zipfile.ZipFile(io.BytesIO(r.read())).extractall(dest)
    n = sum(1 for _ in dest.rglob("*.jpg")) + sum(1 for _ in dest.rglob("*.png"))
    print(f"{slug} v{ver}: {n} images -> {dest}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inspect", nargs="*", default=[])
    ap.add_argument("--download", nargs="*", default=[])
    ap.add_argument("--out", default="D:/smartcane-data/raw/roboflow")
    args = ap.parse_args()
    for s in args.inspect:
        r = inspect(s)
        if "error" in r:
            print(f"{s}: ERROR {r['error']}")
            continue
        top = sorted((r["classes"] or {}).items(), key=lambda kv: -kv[1])[:14]
        print(f"{s}: {r['images']} images, type {r['type']}, v{r['latest']}, licence {r['license']}")
        print(f"    {top}")
    for s in args.download:
        download(s, args.out)


if __name__ == "__main__":
    main()
