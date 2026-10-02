#!/usr/bin/env python3
"""Smart cane - guided bench check of a ToF sensor against a true distance.

Put a target at a measured distance in front of the sensor, then:

    python3 tof_check.py --sensor fwd --true-mm 500 --target "white wall"
    python3 tof_check.py --sensor down --true-mm 300 --target "floor tiles"

It records --seconds of D lines from the ESP32 (the median-of-3 values the
cane acts on), compares them with the true distance and appends one row to
--out. The service must be stopped: it owns the serial port.

Pass limits, fixed before measuring (Phase 2 draft, Step 2.1 starting point):
median absolute error <= max(30 mm, 5 % of the true distance), and at most
5 % of readings invalid ("nothing in range" or sensor not ok).

This is a bench preview, not Step 2.1. Step 2.1 needs raw readings (a
firmware raw-logging mode), more targets and lighting, and outdoor runs.
"""
import argparse
import csv
import math
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from esp32_link import Esp32Link  # noqa: E402


def pct(values, p):
    s = sorted(values)
    return s[max(0, math.ceil(p / 100 * len(s)) - 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sensor", choices=("fwd", "down"), required=True)
    ap.add_argument("--true-mm", type=float, required=True,
                    help="tape-measured distance from the sensor face to the target")
    ap.add_argument("--target", required=True, help="what the sensor sees, e.g. 'white wall'")
    ap.add_argument("--light", default="indoor", help="lighting, e.g. indoor, window, outdoor shade")
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--out", default=os.path.expanduser("~/tof_check.csv"))
    args = ap.parse_args()

    link = Esp32Link(args.port)
    time.sleep(1.0)   # let the stale burst pass (Step 1.1 F5)
    values, invalid, last_seq, rows = [], 0, None, 0
    end = time.time() + args.seconds
    while time.time() < end:
        time.sleep(0.05)
        # last_data changes with every parsed D line, in the old link and the
        # Step 1.5 one alike, so it marks a fresh reading.
        key = link.last_data
        if not key or key == last_seq:
            continue          # no new D line yet
        last_seq = key
        rows += 1
        ok = link.fwd_ok if args.sensor == "fwd" else link.down_ok
        mm = link.fwd_mm if args.sensor == "fwd" else link.down_mm
        if not ok or mm is None:
            invalid += 1
        else:
            values.append(mm)
    link.close()

    if rows == 0:
        sys.exit("no readings: is the service stopped and the ESP32 sending?")
    limit = max(30.0, 0.05 * args.true_mm)
    result = {
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"), "sensor": args.sensor,
        "target": args.target, "light": args.light, "true_mm": args.true_mm,
        "readings": rows, "invalid_rate": round(invalid / rows, 4),
    }
    if values:
        med = statistics.median(values)
        result.update({
            "mean_mm": round(statistics.fmean(values), 1), "median_mm": med,
            "stdev_mm": round(statistics.stdev(values), 1) if len(values) > 1 else 0.0,
            "p5_mm": pct(values, 5), "p95_mm": pct(values, 95),
            "abs_error_mm": round(abs(med - args.true_mm), 1),
            "rel_error": round(abs(med - args.true_mm) / args.true_mm, 4),
        })
    passed = bool(values) and result["abs_error_mm"] <= limit and result["invalid_rate"] <= 0.05
    result.update({"limit_mm": round(limit, 1), "pass": passed})

    new = not os.path.exists(args.out)
    with open(args.out, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(result))
        if new:
            w.writeheader()
        w.writerow(result)
    for k, v in result.items():
        print(f"{k:14s} {v}")
    print("PASS" if passed else "FAIL", f"(appended to {args.out})")


if __name__ == "__main__":
    main()
