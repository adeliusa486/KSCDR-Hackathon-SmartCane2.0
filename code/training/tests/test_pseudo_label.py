#!/usr/bin/env python3
"""Unit test for the box-merging rule in pseudo_label.py (no GPU needed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pseudo_label import class_map, iou, merge_boxes  # noqa: E402

failures = 0


def check(cond, msg):
    global failures
    if not cond:
        failures += 1
        print("FAIL:", msg)


check(abs(iou((0.5, 0.5, 0.2, 0.2), (0.5, 0.5, 0.2, 0.2)) - 1) < 1e-9, "same box IoU 1")
check(iou((0.2, 0.2, 0.1, 0.1), (0.8, 0.8, 0.1, 0.1)) == 0, "disjoint IoU 0")

existing = [(0, (0.5, 0.5, 0.2, 0.4))]                  # a labelled person
props = [(0, (0.51, 0.5, 0.2, 0.4), 0.9),              # same person again
         (14, (0.2, 0.7, 0.3, 0.2), 0.8),              # an unlabelled car
         (14, (0.21, 0.7, 0.3, 0.2), 0.6),             # same car, second teacher
         (14, (0.5, 0.5, 0.2, 0.4), 0.7),              # 'car' exactly on the labelled person
         (14, (0.5, 0.75, 0.3, 0.3), 0.65)]            # car partly behind the person (IoU < 0.6)
added = merge_boxes(existing, props, 0.5)
check(not any(c == 0 for c, _, _ in added), "existing person is not duplicated")
check(not any(b == (0.5, 0.5, 0.2, 0.4) for _, b, _ in added),
      "a box of another class on top of a labelled object is rejected (camel -> cow)")
check(sum(1 for c, _, _ in added if c == 14) == 2, f"car beside, car partly behind ({added})")
check(added[0][2] == 0.8, "highest-confidence proposal wins")
camel = [(13, (0.5, 0.5, 0.4, 0.4))]
check(merge_boxes(camel, [(10, (0.51, 0.5, 0.4, 0.42), 0.8)], 0.5) == [],
      "labelled camel does not also become a cow")

coco = class_map(Path(__file__).resolve().parent.parent / "classes_v2.yaml", "coco")
oiv7 = class_map(Path(__file__).resolve().parent.parent / "classes_v2.yaml", "oiv7")
check(coco["person"] == oiv7["Man"] == oiv7["Person"], "COCO person and OIV7 Man map to one class")
check(coco["dining table"] == oiv7["Table"], "dining table and Table map to table")
check("giraffe" not in coco, "COCO classes outside the list are not mapped")

if failures:
    print(f"{failures} check(s) failed")
    sys.exit(1)
print("all pseudo_label checks passed")
