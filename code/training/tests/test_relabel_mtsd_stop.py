#!/usr/bin/env python3
"""Test relabel_mtsd_stop.py on a synthetic dataset.

    C:/ml/venv/Scripts/python.exe code/training/tests/test_relabel_mtsd_stop.py

Planted: a stop sign stored as traffic sign (must change), a yield sign next
to it (must stay), a stop sign with no label line (dropped as too small at
conversion), a car whose box equals a stop sign box (wrong class, must stay),
a non-MTSD file (untouched), and a second run that must change nothing.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
TOOL = HERE.parent / "relabel_mtsd_stop.py"
failures = 0


def check(cond, msg):
    global failures
    if not cond:
        failures += 1
        print(f"FAIL: {msg}")


SIGN, STOP, CAR = 32, 31, 14
W, H = 4000, 3000


def obj(label, x0, y0, x1, y1):
    return {"label": label, "bbox": {"xmin": x0, "ymin": y0, "xmax": x1, "ymax": y1}}


def line(c, x0, y0, x1, y1):
    return f"{c} {(x0 + x1) / 2 / W:.6f} {(y0 + y1) / 2 / H:.6f} {(x1 - x0) / W:.6f} {(y1 - y0) / H:.6f}"


with tempfile.TemporaryDirectory() as d:
    root, mtsd = Path(d) / "data", Path(d) / "mtsd" / "annotations"
    (root / "labels" / "train").mkdir(parents=True)
    mtsd.mkdir(parents=True)
    (root / "smartcane.yaml.hold").write_text(yaml.safe_dump(
        {"names": {CAR: "car", STOP: "stop sign", SIGN: "traffic sign"}}))
    stop, yld, tiny = (1000, 1000, 1100, 1100), (1200, 1000, 1300, 1100), (10, 10, 14, 14)
    (mtsd / "k1.json").write_text(json.dumps({"width": W, "height": H, "objects": [
        obj("regulatory--stop--g1", *stop), obj("regulatory--yield--g1", *yld),
        obj("regulatory--stop--g10", *tiny)]}))
    (mtsd / "k2.json").write_text(json.dumps({"width": W, "height": H, "objects": [
        obj("regulatory--stop--g1", *stop)]}))
    f1 = root / "labels" / "train" / "mtsd__train__k1.txt"
    f2 = root / "labels" / "train" / "mtsd__val__k2.txt"
    f3 = root / "labels" / "train" / "coco__train2017__x.txt"
    f1.write_text(line(SIGN, *yld) + "\n" + line(SIGN, *stop) + "\n" + line(CAR, 0, 2000, 4000, 3000) + "\n")
    f2.write_text(line(CAR, *stop) + "\n")
    f3.write_text(line(SIGN, *stop) + "\n")
    before = {p: p.read_text() for p in (f1, f2, f3)}

    def run(*extra):
        r = subprocess.run([sys.executable, str(TOOL), "--data", str(root), "--mtsd", str(mtsd.parent),
                            *extra], capture_output=True, text=True)
        check(r.returncode == 0, f"exit {r.returncode}: {r.stderr}")
        return r.stdout

    out = run()
    check("to change: 1" in out, f"dry run count: {out}")
    check({p: p.read_text() for p in before} == before, "dry run changed files")

    out = run("--apply")
    check("changed: 1" in out and "no matching box (dropped as too small at conversion): 2" in out,
          f"apply counts: {out}")
    got = f1.read_text().splitlines()
    check(got == [line(SIGN, *yld), line(STOP, *stop), line(CAR, 0, 2000, 4000, 3000)], f"file 1: {got}")
    check(f2.read_text() == before[f2], "a car box was relabelled")
    check(f3.read_text() == before[f3], "non-MTSD file touched")
    check((root / "mtsd_stop_relabel.csv").read_text().count("\n") == 2, "log should hold 1 change")

    out = run("--apply")
    check("changed: 0" in out and "already stop sign: 1" in out, f"second run: {out}")
    check(f1.read_text().splitlines() == got, "second run changed file 1")

print("PASS" if failures == 0 else f"{failures} FAILURES")
sys.exit(1 if failures else 0)
