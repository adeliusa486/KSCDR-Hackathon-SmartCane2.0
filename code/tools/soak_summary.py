#!/usr/bin/env python3
"""Summarize a power_soak.sh run into per-phase numbers, on the laptop.

    python soak_summary.py RUN_DIR [--json out.json]

Reads RUN_DIR/soak_log.csv and RUN_DIR/kernel_events.log. For every phase
prints duration, EXT5V min/mean, temperature peak, ARM clock min, PMIC power
mean/max, gateway ping loss, detect.py CPU use (under 0.02 s per sample = stuck), and the
throttle bits seen. Counts kernel events by kind. Changes nothing.

get_throttled bits: 0 under-voltage now, 1 freq capped now, 2 throttled now,
3 soft temp limit now, 16-19 the same, "has occurred since boot".
"""
import argparse
import csv
import json
import re
import statistics
from pathlib import Path

BITS = {0: "uv_now", 1: "capped_now", 2: "throttled_now", 3: "soft_temp_now",
        16: "uv_since_boot", 17: "capped_since_boot", 18: "throttled_since_boot",
        19: "soft_temp_since_boot"}

EVENTS = {
    "undervoltage": r"Undervoltage detected",
    "hailo": r"hailo.*(disconnect|error|fail|timeout)",
    "cp210x_timeout": r"cp210x.*-110",
    "usb_disconnect": r"usb .*disconnect",
    "mmc": r"mmc",
    "ext4": r"EXT4-fs",
    "io_error": r"I/O error",
    "oom": r"out of memory",
}


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def summarize(run):
    rows = list(csv.DictReader(open(run / "soak_log.csv", newline="")))
    phases = {}
    for r in rows:
        phases.setdefault(r["phase"], []).append(r)

    out = {"samples": len(rows), "phases": {}}
    for name, rs in phases.items():
        ext = [v for v in (num(r["ext5v_v"]) for r in rs) if v is not None]
        temp = [v for v in (num(r["temp_c"]) for r in rs) if v is not None]
        arm = [v for v in (num(r["arm_hz"]) for r in rs) if v is not None]
        pw = [v for v in (num(r["pmic_w"]) for r in rs) if v is not None]
        lost = sum(1 for r in rs if r["gw_ping_ms"] == "LOST")
        vis = [v for v in (num(r.get("detect_cpu")) for r in rs) if v is not None]
        bits = 0
        for r in rs:
            try:
                bits |= int(r["throttled"], 16)
            except ValueError:
                pass
        mono = [num(r["mono_s"]) for r in rs]
        out["phases"][name] = {
            "samples": len(rs),
            "duration_s": round(mono[-1] - mono[0], 1) if len(rs) > 1 else 0,
            "ext5v_min_v": min(ext) if ext else None,
            "ext5v_mean_v": round(statistics.mean(ext), 4) if ext else None,
            "temp_max_c": max(temp) if temp else None,
            "arm_min_mhz": round(min(arm) / 1e6) if arm else None,
            "pmic_w_mean": round(statistics.mean(pw), 2) if pw else None,
            "pmic_w_max": max(pw) if pw else None,
            "ping_lost": lost,
            "ping_lost_pct": round(100 * lost / len(rs), 2),
            "detect_samples": len(vis),
            "detect_cpu_median": statistics.median(vis) if vis else None,
            "detect_stuck_samples": sum(1 for v in vis if v < 0.02),
            "throttle_bits_seen": [n for b, n in BITS.items() if bits & (1 << b)],
        }

    ev_path = run / "kernel_events.log"
    lines = ev_path.read_text(errors="replace").splitlines() if ev_path.exists() else []
    lines = [l for l in lines if "Modules linked in" not in l]
    out["kernel_events"] = {k: sum(1 for l in lines if re.search(p, l, re.I))
                            for k, p in EVENTS.items()}
    out["undervoltage_times"] = [l.split()[2] for l in lines
                                 if "Undervoltage detected" in l][:50]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    s = summarize(a.run)
    text = json.dumps(s, indent=2)
    print(text)
    if a.json:
        a.json.write_text(text + "\n")


if __name__ == "__main__":
    main()
