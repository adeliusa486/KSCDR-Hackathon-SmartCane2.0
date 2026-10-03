#!/usr/bin/env python3
"""Test clean_pseudo.py on a synthetic dataset.

    C:/ml/venv/Scripts/python.exe code/training/tests/test_clean_pseudo.py

Planted: a bonnet box on an MTSD photo, a wide bottom car on a COCO photo
(must stay), a narrow bottom car on MTSD (must stay), a pseudo stop sign, a
human stop sign and a human car with exactly the same numbers as a pseudo box
(both must stay), and a second run that must change nothing.
"""
import csv
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
CLEAN = HERE.parent / "clean_pseudo.py"
CLASSES = HERE.parent / "classes_v2.yaml"
failures = 0


def check(cond, msg):
    global failures
    if not cond:
        failures += 1
        print(f"FAIL: {msg}")


names = [c["name"] for c in yaml.safe_load(CLASSES.read_text())["classes"]]
CAR, STOP, PERSON = names.index("car"), names.index("stop sign"), names.index("person")
BONNET = (CAR, 0.5, 0.9, 0.9, 0.2)

with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    (root / "labels" / "train").mkdir(parents=True)

    def line(b):
        return f"{b[0]} " + " ".join(f"{v:.6f}" for v in b[1:])

    # image -> (human boxes, pseudo boxes)
    data = {
        "mtsd__train__a": ([(STOP, 0.5, 0.5, 0.05, 0.05), BONNET],      # human bonnet-shaped car
                           [BONNET, (CAR, 0.3, 0.6, 0.1, 0.1)]),
        "mtsd__train__b": ([], [(CAR, 0.5, 0.95, 0.3, 0.1)]),             # narrow: stays
        "coco__train2017__c": ([], [(CAR, 0.5, 0.9, 0.9, 0.2)]),          # not MTSD: stays
        "oiv7__train__d": ([(PERSON, 0.2, 0.2, 0.1, 0.3)], [(STOP, 0.7, 0.3, 0.04, 0.05)]),
    }
    rows = []
    for stem, (human, pseudo) in data.items():
        (root / "labels" / "train" / f"{stem}.txt").write_text(
            "".join(line(b) + "\n" for b in human + pseudo))
        for b in pseudo:
            rows.append(["train", stem + ".jpg", b[0], 0.7, *b[1:], "t.pt"])
    with open(root / "pseudo_labels.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["split", "image", "class", "conf", "cx", "cy", "w", "h", "teacher"])
        w.writerows(rows)
    before = {p.name: p.read_text() for p in (root / "labels" / "train").iterdir()}

    def run(*extra):
        r = subprocess.run([sys.executable, str(CLEAN), "--data", str(root), *extra],
                           capture_output=True, text=True)
        check(r.returncode == 0, f"exit {r.returncode}: {r.stderr}")
        return r.stdout

    out = run()
    check("bonnet: 1 to remove" in out and "stop sign: 1 to remove" in out, f"dry-run counts: {out}")
    after_dry = {p.name: p.read_text() for p in (root / "labels" / "train").iterdir()}
    check(after_dry == before, "dry run changed label files")
    check(not (root / "pseudo_removed.csv").exists(), "dry run wrote the removal log")

    out = run("--apply")
    check("removed: 2 in 2 files" in out, f"apply counts: {out}")
    lab = lambda s: [l for l in (root / "labels" / "train" / f"{s}.txt").read_text().splitlines() if l]
    a = lab("mtsd__train__a")
    check(a == [line((STOP, 0.5, 0.5, 0.05, 0.05)), line(BONNET), line((CAR, 0.3, 0.6, 0.1, 0.1))],
          f"file a wrong, human boxes must stay and one bonnet copy go: {a}")
    check(len(lab("mtsd__train__b")) == 1, "narrow MTSD car was removed")
    check(len(lab("coco__train2017__c")) == 1, "COCO wide car was removed")
    check(lab("oiv7__train__d") == [line((PERSON, 0.2, 0.2, 0.1, 0.3))], "pseudo stop sign not removed")
    with open(root / "pseudo_labels.csv", newline="") as f:
        check(len(list(csv.DictReader(f))) == 3, "pseudo_labels.csv should list 3 boxes")
    with open(root / "pseudo_removed.csv", newline="") as f:
        rem = list(csv.DictReader(f))
    check(sorted(r["rule"] for r in rem) == ["bonnet", "stop sign"], f"removal log wrong: {rem}")

    snap = {p.name: p.read_text() for p in (root / "labels" / "train").iterdir()}
    out = run("--apply")
    check("removed: 0" in out, f"second run removed something: {out}")
    check({p.name: p.read_text() for p in (root / "labels" / "train").iterdir()} == snap,
          "second run changed files")

print("PASS" if failures == 0 else f"{failures} FAILURES")
sys.exit(1 if failures else 0)
