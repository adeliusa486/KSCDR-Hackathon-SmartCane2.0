#!/usr/bin/env python3
"""Smart cane - remove known-bad teacher boxes after pseudo_label.py.

A visual check on 3 Oct 2026 found two kinds of wrong boxes the teachers add:

  * bonnet: on Mapillary dashcam photos the COCO teacher calls the recording
    car's own bonnet or dashboard "car". A wide box (w > 0.6) touching the
    bottom edge of an MTSD photo was the bonnet in 8 of 9 random samples.
  * stop sign: the COCO teacher calls logos (VW, 76), the backs of round signs
    and a European "no left turn" sign "stop sign". About 4 of 16 random
    samples were stop-sign faces. Stop signs keep their human labels.

Only boxes listed in pseudo_labels.csv are touched, so human labels can never
be removed. Each removed box is written to pseudo_removed.csv and the rows
are dropped from pseudo_labels.csv, so the audit trail stays true. Safe to
run twice: a box already gone is skipped.

    python clean_pseudo.py --data D:/smartcane-data/merged_v2           # dry run
    python clean_pseudo.py --data D:/smartcane-data/merged_v2 --apply
"""
import argparse
import collections
import csv
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent


def rules(names):
    car = names.index("car")
    stop = names.index("stop sign")

    def bonnet(r):
        cy, w, h = float(r["cy"]), float(r["w"]), float(r["h"])
        return (r["image"].startswith("mtsd__") and int(r["class"]) == car
                and cy + h / 2 > 0.97 and w > 0.6)

    def stop_sign(r):
        return int(r["class"]) == stop

    return {"bonnet": bonnet, "stop sign": stop_sign}


def box_key(fields):
    """Label line fields -> (class, cx, cy, w, h) rounded the way they were written."""
    return (int(fields[0]),) + tuple(round(float(v), 6) for v in fields[1:5])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="dataset folder pseudo_label.py ran on")
    ap.add_argument("--classes", default=str(HERE / "classes_v2.yaml"))
    ap.add_argument("--apply", action="store_true", help="change files (default: dry run)")
    args = ap.parse_args()

    root = Path(args.data)
    names = [c["name"] for c in yaml.safe_load(Path(args.classes).read_text())["classes"]]
    checks = rules(names)

    with open(root / "pseudo_labels.csv", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)

    drop = collections.defaultdict(list)    # label file -> [(key, rule, row)]
    keep = []
    per_rule = collections.Counter()
    for r in rows:
        hit = next((n for n, test in checks.items() if test(r)), None)
        if hit is None:
            keep.append(r)
            continue
        per_rule[hit] += 1
        lbl = root / "labels" / r["split"] / (Path(r["image"]).stem + ".txt")
        key = (int(r["class"]),) + tuple(round(float(r[k]), 6) for k in ("cx", "cy", "w", "h"))
        drop[lbl].append((key, hit, r))

    print(f"pseudo boxes listed: {len(rows)}")
    for n, k in per_rule.items():
        print(f"  {n}: {k} to remove")
    print(f"  kept: {len(keep)}")

    removed = missing = 0
    log_rows = []
    for lbl, items in drop.items():
        lines = lbl.read_text().splitlines() if lbl.exists() else []
        wanted = collections.Counter(k for k, _, _ in items)
        # pseudo_label.py appends after the human lines, so match from the end:
        # a human box with identical numbers is never the one removed.
        out = []
        for line in reversed(lines):
            f = line.split()
            if len(f) == 5:
                k = box_key(f)
                if wanted[k] > 0:
                    wanted[k] -= 1
                    removed += 1
                    continue
            out.append(line)
        out.reverse()
        missing += sum(wanted.values())
        for k, hit, r in items:
            log_rows.append({**r, "rule": hit})
        if args.apply:
            lbl.write_text("".join(l + "\n" for l in out))

    print(f"label lines {'removed' if args.apply else 'that would be removed'}: {removed}"
          f" in {len(drop)} files, not found (already removed): {missing}")

    if args.apply:
        log_path = root / "pseudo_removed.csv"
        new = not log_path.exists()
        with open(log_path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields + ["rule"])
            if new:
                w.writeheader()
            w.writerows(log_rows)
        with open(root / "pseudo_labels.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(keep)
        print(f"logged to {log_path}, pseudo_labels.csv now lists {len(keep)} boxes")
    else:
        print("dry run, nothing changed. Add --apply to change files.")


if __name__ == "__main__":
    main()
