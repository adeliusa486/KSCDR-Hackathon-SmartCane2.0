#!/usr/bin/env python3
"""Smart cane - merge, remap and split datasets without leakage (Phase 3 prep).

prepare_datasets.py downloads sources and writes smartcane.yaml, but nothing
filled images/train and images/val, and LABEL_ALIASES was never applied. This
script is that missing step. It also enforces the Phase 3 Step 3.7 rules:

  * Split by group, never by image. A group is a session, a location or one
    source video, given per source as a regex on the file name. Frames of one
    dashcam clip never end up on both sides of a split.
  * Exact and near duplicates (a 64-bit difference hash, Hamming distance
    <= 3) join their groups, even across sources. So no duplicate can cross
    a split either. Whole connected groups are assigned to a split.
  * Public datasets go to train and val only. The test split holds only
    sources marked "public: false" (cane-camera recordings).
  * Labels are remapped through LABEL_ALIASES onto classes.yaml. Unknown
    classes are dropped and counted, never silently renamed.
  * Corrupt images, bad label lines and images without labels are reported.

Every source is in YOLO layout: images somewhere under <path>/images, labels
under <path>/labels with the same relative path and a .txt suffix. The
source's own train/val/test folders are ignored: everything is pooled and
re-split.

    python build_dataset.py --sources sources.yaml --out C:/ml/smartcane/merged

sources.yaml:

    sources:
      - name: bharat_pothole
        path: C:/ml/smartcane/data/raw/bharat_pothole
        names: [pothole]              # the source's class list, in its order
        group: '^(?P<g>.+)_frame\\d+$'  # regex on the image stem
        public: true
      - name: cane_2026_11_03_market
        path: C:/ml/smartcane/data/cane/2026-11-03_market
        names_from: data.yaml         # or read names from the source's yaml
        group: '^(?P<g>.+)$'          # the whole session is one group
        public: false

Without a group regex every image is its own group, which is right only for
independent still photos. If the stems look like numbered video frames the
audit warns.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_datasets import COCO, LABEL_ALIASES, load_classes  # noqa: E402

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
NEAR_DUP_BITS = 3        # Hamming distance on the 64-bit dHash
VIDEO_HINT_MIN = 5       # numbered images sharing a prefix worth checking
VIDEO_ALIKE_BITS = 12    # neighbours this close look like video (unrelated
                         # images differ by about 32 of 64 bits)


def dhash(img):
    """64-bit difference hash: robust to resizing and recompression."""
    g = img.convert("L").resize((9, 8), Image.BILINEAR)
    px = list(g.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (px[row * 9 + col] > px[row * 9 + col + 1])
    return bits


def split_of(key, fractions, public):
    """Deterministic split from a hash of the group key."""
    h = int(hashlib.sha1(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    train, val, _test = fractions
    if public:   # no test for public data: rescale train/val to fill [0, 1)
        return "train" if h < train / (train + val) else "val"
    return "train" if h < train else "val" if h < train + val else "test"


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def source_names(src):
    if src.get("names") == "coco":
        return list(COCO)
    if "names" in src:
        return [str(n) for n in src["names"]]
    data = yaml.safe_load((Path(src["path"]) / src["names_from"]).read_text())
    names = data["names"]
    return [names[i] for i in sorted(names)] if isinstance(names, dict) else list(names)


def target_index(name, classes, src, src_map=None):
    """Index of the class a source label becomes, or None to drop it.

    With a v2 class list (src_map), the mapping is exact: "<dataset>:<label>"
    as written in classes_v2.yaml, case and all. Without one, the old
    lower-cased LABEL_ALIASES lookup onto classes.yaml applies.
    """
    if src_map is not None:
        target = src_map.get(f"{src.get('dataset', src['name'])}:{name}")
        return classes.index(target) if target is not None else None
    n = str(name).strip().lower()
    n = LABEL_ALIASES.get(n, n)
    return classes.index(n) if n in classes else None


def load_v2(path):
    """Class names and the "<dataset>:<label>" -> class map from classes_v2.yaml."""
    cfg = yaml.safe_load(Path(path).read_text())
    names = [c["name"] for c in cfg["classes"]]
    src_map = {s: c["name"] for c in cfg["classes"] for s in c["src"]}
    return names, src_map


def scan(src, classes, audit, src_map=None):
    """Yield one record per usable image of a source."""
    root = Path(src["path"])
    names = source_names(src)
    group_re = re.compile(src["group"]) if src.get("group") else None
    stems = []
    # Any image under a folder called "images"; its label sits at the same
    # place under the matching "labels" folder. Covers root/images/<split>/x
    # (YOLO, FiftyOne) and root/<split>/images/x (Roboflow).
    images = sorted(p for p in root.rglob("*") if p.suffix.lower() in IMAGE_EXT
                    and "images" in p.relative_to(root).parts)
    cap = src.get("max_images")
    if cap and len(images) > cap:
        # deterministic subset: the same photos on every rebuild
        images = sorted(images, key=lambda p: hashlib.sha1(p.name.encode()).hexdigest())[:cap]
        audit["capped"][src["name"]] = cap
    for img_path in images:
        rel = img_path.relative_to(root)
        parts = list(rel.parts)
        i = len(parts) - 1 - parts[::-1].index("images")
        parts[i] = "labels"
        label_path = (root / Path(*parts)).with_suffix(".txt")
        # the output name leaves the "images" folder out, as before
        rel = Path(*(rel.parts[:i] + rel.parts[i + 1:]))
        try:
            with Image.open(img_path) as im:
                im.verify()
            with Image.open(img_path) as im:
                dh = dhash(im)
        except Exception as e:
            audit["corrupt_images"].append(f"{src['name']}/{rel}: {e}")
            continue
        md5 = hashlib.md5(img_path.read_bytes()).hexdigest()

        lines, kept = [], Counter()
        if not label_path.exists():
            audit["missing_labels"][src["name"]] += 1
        else:
            for ln, raw in enumerate(label_path.read_text().splitlines(), 1):
                parts = raw.split()
                if not parts:
                    continue
                try:
                    cls = int(parts[0])
                    box = [float(v) for v in parts[1:5]]
                    ok = len(parts) == 5 and all(0 <= v <= 1 for v in box) \
                        and box[2] > 0 and box[3] > 0
                except ValueError:
                    ok = False
                if not ok or not (0 <= cls < len(names)):
                    audit["bad_label_lines"].append(f"{src['name']}/{rel}:{ln}: {raw}")
                    continue
                new = target_index(names[cls], classes, src, src_map)
                if new is None:
                    audit["dropped_classes"][f"{src['name']}:{names[cls]}"] += 1
                    continue
                kept[classes[new]] += 1
                lines.append(f"{new} " + " ".join(parts[1:5]))
            if not lines:
                audit["empty_after_remap"][src["name"]] += 1

        stem = img_path.stem
        if group_re:
            m = group_re.search(stem)
            if not m:
                audit["group_regex_miss"].append(f"{src['name']}/{rel}")
                continue
            g = m.group("g") if "g" in group_re.groupindex else m.group(0)
        else:
            g = str(rel.with_suffix(""))
            stems.append((stem, dh))
        yield {"source": src["name"], "public": bool(src.get("public", True)),
               "rel": rel, "img": img_path, "lines": lines, "classes": kept,
               "group": f"{src['name']}:{g}", "md5": md5, "dhash": dh}

    # No group regex: are these numbered video frames? Numbering alone proves
    # nothing (img_0001 ... img_0030 can be unrelated photos). Video shows as
    # neighbouring numbers that look alike. Near duplicates (<= 3 bits) are
    # already merged, so this catches frames that differ more than that.
    by_prefix = defaultdict(list)
    for stem, dh in stems:
        m = re.match(r"^(.*?)(\d+)$", stem)
        if m:
            by_prefix[m.group(1)].append((int(m.group(2)), dh))
    for prefix, frames in by_prefix.items():
        if len(frames) < VIDEO_HINT_MIN:
            continue
        frames.sort()
        dist = [bin(a[1] ^ b[1]).count("1") for a, b in zip(frames, frames[1:])]
        alike = sum(d <= VIDEO_ALIKE_BITS for d in dist) / len(dist)
        if alike >= 0.5:
            audit["video_frame_warnings"].append(
                f"{src['name']}: no group regex, but {len(frames)} images "
                f"'{prefix}<n>' look like neighbouring video frames ({alike:.0%} "
                f"of neighbours within {VIDEO_ALIKE_BITS} bits). Set 'group'.")


def link_duplicates(records, uf, audit):
    by_md5 = defaultdict(list)
    for i, r in enumerate(records):
        by_md5[r["md5"]].append(i)
    for idx in by_md5.values():
        for j in idx[1:]:
            uf.union(records[idx[0]]["group"], records[j]["group"])
            audit["exact_duplicates"] += 1
    # Near duplicates: 4 bands of 16 bits. Hamming <= 3 means at least one
    # band matches exactly (pigeonhole), so only band-mates are compared.
    bands = defaultdict(list)
    for i, r in enumerate(records):
        for b in range(4):
            bands[(b, (r["dhash"] >> (16 * b)) & 0xFFFF)].append(i)
    seen = set()
    for idx in bands.values():
        for a_i, a in enumerate(idx):
            for b in idx[a_i + 1:]:
                if (a, b) in seen:
                    continue
                seen.add((a, b))
                if bin(records[a]["dhash"] ^ records[b]["dhash"]).count("1") <= NEAR_DUP_BITS:
                    if records[a]["md5"] != records[b]["md5"]:
                        audit["near_duplicates"] += 1
                    uf.union(records[a]["group"], records[b]["group"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--split", default="0.8,0.1,0.1", help="train,val,test fractions")
    ap.add_argument("--copy", action="store_true", help="copy files instead of hard links")
    ap.add_argument("--classes", help="classes_v2.yaml: exact dataset:label mapping. "
                                      "Without it, classes.yaml and LABEL_ALIASES")
    args = ap.parse_args()
    fractions = [float(v) for v in args.split.split(",")]
    if args.classes:
        classes, src_map = load_v2(args.classes)
    else:
        _, classes = load_classes()
        src_map = None
    sources = yaml.safe_load(Path(args.sources).read_text())["sources"]

    audit = {"corrupt_images": [], "bad_label_lines": [], "group_regex_miss": [],
             "video_frame_warnings": [], "missing_labels": Counter(),
             "empty_after_remap": Counter(), "dropped_classes": Counter(),
             "exact_duplicates": 0, "near_duplicates": 0, "capped": {}}
    records = []
    for src in sources:
        records.extend(scan(src, classes, audit, src_map))

    uf = UnionFind()
    for r in records:
        uf.find(r["group"])
    link_duplicates(records, uf, audit)

    # A component holding ANY public image never goes to test. The test split
    # stays pure cane-camera data, and a cane recording that duplicates a
    # public image cannot drag that public image into test.
    comp_has_public = defaultdict(bool)
    for r in records:
        comp_has_public[uf.find(r["group"])] |= r["public"]

    out = Path(args.out)
    if out.exists():
        sys.exit(f"{out} exists. Use a new folder per build, the old one is evidence.")
    counts = defaultdict(Counter)
    comp_split = {}
    for r in records:
        comp = uf.find(r["group"])
        split = comp_split.setdefault(comp, split_of(comp, fractions, comp_has_public[comp]))
        name = f"{r['source']}__{str(r['rel'].with_suffix('')).replace(os.sep, '__')}"
        img_dst = out / "images" / split / (name + r["img"].suffix.lower())
        lbl_dst = out / "labels" / split / (name + ".txt")
        img_dst.parent.mkdir(parents=True, exist_ok=True)
        lbl_dst.parent.mkdir(parents=True, exist_ok=True)
        if args.copy:
            shutil.copy2(r["img"], img_dst)
        else:
            try:
                os.link(r["img"], img_dst)
            except OSError:
                shutil.copy2(r["img"], img_dst)
        lbl_dst.write_text("\n".join(r["lines"]) + ("\n" if r["lines"] else ""))
        counts[split]["_images"] += 1
        counts[split].update(r["classes"])
        counts[split][f"_source:{r['source']}"] += 1

    # Leakage self-check: no group and no duplicate component in two splits.
    split_by_group = defaultdict(set)
    for r in records:
        split_by_group[r["group"]].add(comp_split[uf.find(r["group"])])
    leaks = [g for g, s in split_by_group.items() if len(s) > 1]

    (out / "smartcane.yaml").write_text(yaml.safe_dump({
        "path": str(out).replace("\\", "/"), "train": "images/train",
        "val": "images/val", "test": "images/test",
        "names": {i: n for i, n in enumerate(classes)}}, sort_keys=False))
    report = {
        "sources": [s["name"] for s in sources], "split_fractions": fractions,
        "images": len(records), "groups": len(split_by_group),
        "components": len(comp_split), "leaking_groups": leaks,
        "per_split": {k: dict(v) for k, v in counts.items()},
        **{k: (dict(v) if isinstance(v, Counter) else v) for k, v in audit.items()},
    }
    (out / "audit.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({k: report[k] for k in ("images", "groups", "components",
                      "leaking_groups", "exact_duplicates", "near_duplicates")}))
    print("per split:", {k: v["_images"] for k, v in counts.items()})
    for w in audit["video_frame_warnings"]:
        print("WARNING", w)
    if leaks:
        sys.exit(f"LEAK: {len(leaks)} groups in more than one split")


if __name__ == "__main__":
    main()
