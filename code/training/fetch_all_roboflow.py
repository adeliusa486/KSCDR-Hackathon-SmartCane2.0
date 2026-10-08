#!/usr/bin/env python3
"""Download every set in roboflow_sources.yaml that is not on disk yet, then
keep one copy per original photo (dedupe_roboflow.py). Needs ROBOFLOW_API_KEY.

    python fetch_all_roboflow.py --out D:/smartcane-data/raw/roboflow
"""
import argparse
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from dedupe_roboflow import dedupe  # noqa: E402
from roboflow_fetch import download  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="D:/smartcane-data/raw/roboflow")
    args = ap.parse_args()
    reg = yaml.safe_load((HERE / "roboflow_sources.yaml").read_text(encoding="utf-8"))
    out = Path(args.out)
    failed = []
    for short, v in reg.items():
        ws, proj = v["project"].split("/")
        dest = out / f"{ws}__{proj}__v{v['version']}"
        if not dest.exists():
            try:
                download(f"{v['project']}:{v['version']}", out)
            except Exception as e:
                print(f"{short}: FAILED {type(e).__name__}: {e}", flush=True)
                failed.append(short)
                continue
        kept, removed = dedupe(dest)
        print(f"{short}: {kept} original photos, {removed} augmented copies removed", flush=True)
    print("failed:", failed or "none")


if __name__ == "__main__":
    main()
