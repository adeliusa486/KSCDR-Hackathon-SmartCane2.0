#!/usr/bin/env python3
"""Smart cane - keep one copy per original photo in Roboflow exports.

Roboflow versions are often exported with augmentation: each original photo
appears many times as "<original>_<ext>.rf.<hash>.jpg", rotated, cropped or
recoloured, sometimes spread over train, valid and test. adli/pillar v4 held
17,450 files for about 323 photos. Used as is, that overweights the class
and puts copies of one photo on both sides of a split, so test accuracy
looks better than it is.

This keeps one copy per original, preferring valid/test (Roboflow does not
augment those), and deletes the rest with their labels. Ultralytics does its
own augmentation during training.

    python dedupe_roboflow.py "D:/smart cane 2.0/datasets/raw/roboflow"
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

# Everything before ".rf." is the original photo. Most names carry the
# original extension ("x_jpg.rf.<hash>"), some do not ("x_-Picture.rf.<hash>",
# the stroller sets), so the extension is not required.
ORIG = re.compile(r"^(?P<orig>.+?)\.rf\.[0-9a-f]+$", re.I)
PREFER = {"valid": 0, "test": 1, "train": 2}


def dedupe(project):
    groups = defaultdict(list)
    for img in project.rglob("*"):
        if img.suffix.lower() not in {".jpg", ".jpeg", ".png"} or img.parent.name != "images":
            continue
        m = ORIG.match(img.stem)
        groups[m.group("orig") if m else img.stem].append(img)
    removed = 0
    for orig, imgs in groups.items():
        imgs.sort(key=lambda p: (PREFER.get(p.parent.parent.name, 3), p.name))
        for extra in imgs[1:]:
            label = extra.parent.parent / "labels" / (extra.stem + ".txt")
            extra.unlink()
            if label.exists():
                label.unlink()
            removed += 1
    return len(groups), removed


def main():
    root = Path(sys.argv[1])
    for project in sorted(p for p in root.iterdir() if p.is_dir()):
        kept, removed = dedupe(project)
        print(f"{project.name}: kept {kept} originals, removed {removed} copies")


if __name__ == "__main__":
    main()
