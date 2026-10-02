#!/usr/bin/env python3
"""Laptop test for detect.py --trace / --frames and tools/trace_summary.py.

Runs the real detect.py against the stand-in picamera2 in tests/fakes
(frames at --fps, SensorTimestamp 40 ms before delivery on CLOCK_BOOTTIME,
13 ms per inference) and checks that the summary recovers those numbers and
that the printed reports still match what speak_detect.py parses.

    python3 code/tests/test_detect_trace.py      (Linux: needs CLOCK_BOOTTIME)
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(HERE)
REPORT = re.compile(r"^\[\s*[\d.]+\s*fps\]\s*(.*)$")   # copied from speak_detect.py

failures = 0


def check(cond, msg):
    global failures
    if not cond:
        failures += 1
        print(f"FAIL: {msg}")


with tempfile.TemporaryDirectory() as tmp:
    hef = os.path.join(tmp, "fake.hef")
    open(hef, "w").close()
    trace = os.path.join(tmp, "trace.csv")
    env = dict(os.environ, PYTHONPATH=os.path.join(HERE, "fakes"))
    out = subprocess.run(
        [sys.executable, "-u", os.path.join(CODE, "detect.py"), "--model", hef,
         "--fps", "30", "--interval", "0.3", "--conf", "0.25", "--all-classes",
         "--frames", "150", "--trace", trace],
        env=env, capture_output=True, text=True, timeout=60)
    check(out.returncode == 0, f"detect.py exit {out.returncode}: {out.stderr[-500:]}")

    reports = [l for l in out.stdout.splitlines() if REPORT.match(l)]
    check(len(reports) >= 10, f"report lines printed ({len(reports)})")
    check(all("person ahead" in l for l in reports), "fake person reported ahead")

    rows = open(trace).read().splitlines()
    check(len(rows) == 151, f"one trace row per frame plus header ({len(rows)})")

    s = subprocess.run([sys.executable, os.path.join(CODE, "tools", "trace_summary.py"),
                        trace, "--skip", "10"], capture_output=True, text=True)
    print(s.stdout)
    summary = json.load(open(trace.replace(".csv", "_summary.json")))
    st = summary["stages_ms"]
    check(28 <= summary["fps"] <= 31, f"fps near 30 ({summary['fps']})")
    check(12.5 <= st["inference"]["p50"] <= 20, f"inference p50 near 13 ms ({st['inference']['p50']})")
    check(38 <= st["sensor_to_frame_if_boottime"]["p50"] <= 45,
          f"sensor-to-frame near 40 ms on BOOTTIME ({st['sensor_to_frame_if_boottime']['p50']})")
    for k in ("p50", "p90", "p95", "p99", "max"):
        check(k in st["pipeline"], f"pipeline has {k}")

if failures:
    print(f"{failures} check(s) failed")
    sys.exit(1)
print("all detect trace checks passed")
