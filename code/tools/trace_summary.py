#!/usr/bin/env python3
"""Smart cane - summarise a detect.py --trace CSV (Phase 3 Step 3.0).

Prints P50, P90, P95, P99, mean and max for each stage, and writes the same
as JSON next to the CSV.

    python3 trace_summary.py trace.csv [--skip 30]

Stages, all from time.monotonic_ns() stamps:
    frame_interval   capture to capture, the real frame rate
    copy             request returned -> frame array ready
    inference        frame ready -> hailo.run returned
    postprocess      hailo.run returned -> detections decoded and ranked
    pipeline         request returned -> detections ready
    sensor_to_frame  SensorTimestamp -> request returned. Reported twice,
                     once assuming the sensor clock is CLOCK_BOOTTIME and once
                     CLOCK_MONOTONIC. The physically sensible one is positive
                     and below a few frame times. Step 3.0 settles which.

--skip drops the first rows: auto-exposure and caches settle at start.
"""
import argparse
import csv
import json
import math
import statistics


def pct(values, p):
    s = sorted(values)
    return s[max(0, math.ceil(p / 100 * len(s)) - 1)]


def stats(values):
    if not values:
        return {"n": 0}
    return {"n": len(values),
            "p50": round(pct(values, 50), 3), "p90": round(pct(values, 90), 3),
            "p95": round(pct(values, 95), 3), "p99": round(pct(values, 99), 3),
            "mean": round(statistics.fmean(values), 3), "max": round(max(values), 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--skip", type=int, default=30)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.csv)))[args.skip:]
    ms = lambda a, b: (int(b) - int(a)) / 1e6
    stage = {
        "frame_interval": [ms(a["capture_ns"], b["capture_ns"]) for a, b in zip(rows, rows[1:])],
        "copy": [ms(r["capture_ns"], r["frame_ready_ns"]) for r in rows],
        "inference": [ms(r["frame_ready_ns"], r["inference_end_ns"]) for r in rows],
        "postprocess": [ms(r["inference_end_ns"], r["postprocess_end_ns"]) for r in rows],
        "pipeline": [ms(r["capture_ns"], r["postprocess_end_ns"]) for r in rows],
    }
    with_ts = [r for r in rows if r["sensor_ts_ns"]]
    stage["sensor_to_frame_if_boottime"] = [
        (int(r["capture_ns"]) - (int(r["sensor_ts_ns"]) - int(r["boottime_minus_mono_ns"]))) / 1e6
        for r in with_ts]
    stage["sensor_to_frame_if_monotonic"] = [
        (int(r["capture_ns"]) - int(r["sensor_ts_ns"])) / 1e6 for r in with_ts]

    out = {"csv": args.csv, "rows_used": len(rows), "skipped": args.skip,
           "fps": round(1000 / statistics.fmean(stage["frame_interval"]), 2)
           if stage["frame_interval"] else None,
           "stages_ms": {k: stats(v) for k, v in stage.items()}}
    with open(args.csv.rsplit(".", 1)[0] + "_summary.json", "w") as f:
        json.dump(out, f, indent=2)

    print(f"{args.csv}: {len(rows)} frames, {out['fps']} fps")
    print(f"{'stage (ms)':30s} {'p50':>8s} {'p90':>8s} {'p95':>8s} {'p99':>8s} {'max':>8s}")
    for k, s in out["stages_ms"].items():
        if s["n"]:
            print(f"{k:30s} {s['p50']:8.2f} {s['p90']:8.2f} {s['p95']:8.2f} "
                  f"{s['p99']:8.2f} {s['max']:8.2f}")


if __name__ == "__main__":
    main()
