#!/usr/bin/env python3
"""Build the project website from web/site.html and the repository's data.

    python web/build.py

Writes web/_site/, which GitHub Actions deploys to GitHub Pages:
  index.html   the project page
  live.html    the cane's live dashboard: connects to a cane through its
               tunnel, or plays web/replay/ if present
  admin.html   the owner's page: log in (the cane checks the password),
               live view, Wi-Fi, Bluetooth (code/admin_dashboard.html)
  assets/      figures and charts from docs/

The objects list is generated from the model's label file, the training
counts and the per-class validation, so the page cannot drift from the model.
"""
import csv
import json
import os
import shutil
import sys

WEB = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(WEB)
sys.path.insert(0, os.path.join(ROOT, "docs"))
sys.path.insert(0, os.path.join(ROOT, "code"))
from make_objects import GROUPS  # noqa: E402

PAGES_URL = "https://adeliusa486.github.io/OmniWalk/"
ASSETS = ["docs/figures/sensor_geometry.svg",
          "docs/figures/cross_section.svg", "docs/figures/live_dashboard.jpg"] + \
         [f"docs/charts/{n}-{m}.svg" for n in ("camera-path", "training", "safety-classes", "dataset")
          for m in ("light", "dark")]


def objects():
    counts = {r["class"]: int(r["train_boxes"])
              for r in csv.DictReader(open(os.path.join(ROOT, "data/merged_v2/class_counts.csv")))}
    val = {r["class"]: float(r["mAP50"] or 0)
           for r in csv.DictReader(open(os.path.join(ROOT, "docs/results/v3_per_class.csv")))}
    return [{"name": c, "group": g, "map50": round(val.get(c, 0.0), 3), "boxes": counts.get(c, 0)}
            for g, cs in GROUPS for c in cs]


def render(live_url):
    src = open(os.path.join(WEB, "site.html"), encoding="utf-8").read()
    head, body = src.split("<!--BODY-->", 1)
    data = json.dumps(objects(), separators=(",", ":"))
    body = body.replace("/*OBJECTS*/[]/*END*/", data).replace("LIVE_URL", live_url)
    return head.strip(), body.strip()


def main():
    site = os.path.join(WEB, "_site")
    shutil.rmtree(site, ignore_errors=True)
    os.makedirs(os.path.join(site, "assets"))

    head, body = render("live.html")
    with open(os.path.join(site, "index.html"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                 '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                 '<meta name="description" content="An offline AI white cane: 152 objects with direction '
                 'and distance, obstacle and drop-off alerts by vibration, a one-button assistant.">\n'
                 f"{head}\n</head>\n<body>\n{body}\n</body>\n</html>\n")
    shutil.copy2(os.path.join(ROOT, "code", "demo_dashboard.html"), os.path.join(site, "live.html"))
    shutil.copy2(os.path.join(ROOT, "code", "admin_dashboard.html"), os.path.join(site, "admin.html"))
    if os.path.isdir(os.path.join(WEB, "replay")):
        shutil.copytree(os.path.join(WEB, "replay"), os.path.join(site, "replay"))
    open(os.path.join(site, ".nojekyll"), "w").close()
    for a in ASSETS:
        shutil.copy2(os.path.join(ROOT, a), os.path.join(site, "assets", os.path.basename(a)))
    print(f"built web/_site for {PAGES_URL}: {len(objects())} objects, {len(ASSETS)} assets")


if __name__ == "__main__":
    main()
