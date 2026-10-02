#!/usr/bin/env python3
"""Smart cane - record the ESP32 serial stream and summarise it.

Bench measurement tool for the safety co-processor. Logs every line with the
Pi's receive time and writes:

    <out>.csv    one row per D line: host_ns, esp_ms, fwd, down, fok, dok, base
    <out>.log    every other line (I / E / H) with its host time
    <out>.json   report rate, interval percentiles, gaps, per-sensor rates and
                 distance stats, error / hazard counts, boot timing

The smartcane service must be stopped first. Two readers on one tty split the
bytes between them and both see garbage.

The port is opened the same way as esp32_link.py (default DTR/RTS, see its
docstring), so a plain capture does NOT reset the ESP32. --reset does it on
purpose and times the boot: reset release -> boot banner -> first D line.

    python3 esp32_capture.py --seconds 60 --send T --send S --out /tmp/esp
    python3 esp32_capture.py --reset --seconds 10 --out /tmp/boot
"""
import argparse
import json
import math
import statistics
import time

import serial

REPORT_MS = 50          # firmware REPORT_MS, the expected D-line period


def pct(values, p):
    """Nearest-rank percentile, no numpy needed."""
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, math.ceil(p / 100 * len(s)) - 1))
    return s[k]


def summary(values):
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "min": min(values), "max": max(values),
        "mean": round(statistics.fmean(values), 2),
        "median": statistics.median(values),
        "stdev": round(statistics.stdev(values), 2) if len(values) > 1 else 0.0,
        "p5": pct(values, 5), "p50": pct(values, 50), "p95": pct(values, 95),
        "p99": pct(values, 99),
    }


def reset_esp32(ser):
    """Pulse EN through the DevKit's auto-reset transistors, boot normally.

    EN is pulled low only while RTS is asserted and DTR is not. GPIO0 is
    pulled low only while DTR is asserted and RTS is not. So: drop DTR (EN low,
    since RTS is still up), wait, then drop RTS (EN released with GPIO0 high,
    i.e. normal boot, not the download mode).
    """
    ser.dtr = False
    ser.rts = True
    time.sleep(0.1)
    ser.rts = False
    return time.monotonic_ns()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--send", action="append", default=[],
                    help="command sent 1 s after start, e.g. T, S, A0")
    ap.add_argument("--reset", action="store_true",
                    help="reset the ESP32 first and time its boot")
    ap.add_argument("--out", required=True, help="output path prefix")
    args = ap.parse_args()

    ser = serial.Serial(args.port, 115200, timeout=0.05)
    t_release = None
    if args.reset:
        t_release = reset_esp32(ser)
    else:
        # Drop the backlog that piled up while nobody was reading.
        ser.reset_input_buffer()

    t0 = time.monotonic_ns()
    end = t0 + int(args.seconds * 1e9)
    sent = False
    rows, other = [], []
    buf = b""
    bad_lines = 0
    while time.monotonic_ns() < end:
        if not sent and time.monotonic_ns() - t0 > 1e9:
            for c in args.send:
                ser.write((c + "\n").encode())
                other.append((time.monotonic_ns(), f"> {c}"))
                time.sleep(0.2)
            sent = True
        buf += ser.read(ser.in_waiting or 1)
        now = time.monotonic_ns()
        while b"\n" in buf:
            raw, buf = buf.split(b"\n", 1)
            line = raw.decode(errors="replace").strip()
            if line.startswith("D "):
                try:
                    _, ms, fwd, down, fok, dok, base = line.split()
                    rows.append((now, int(ms), int(fwd), int(down),
                                 int(fok), int(dok), int(base)))
                except ValueError:
                    bad_lines += 1
                    other.append((now, "BAD " + line))
            elif line:
                other.append((now, line))
    ser.close()

    with open(args.out + ".csv", "w") as f:
        f.write("host_ns,esp_ms,fwd_mm,down_mm,fwd_ok,down_ok,ground_mm\n")
        for r in rows:
            f.write(",".join(map(str, r)) + "\n")
    with open(args.out + ".log", "w") as f:
        for t, line in other:
            f.write(f"{(t - t0) / 1e6:10.1f} ms  {line}\n")

    host_iv = [(b[0] - a[0]) / 1e6 for a, b in zip(rows, rows[1:])]
    esp_iv = [b[1] - a[1] for a, b in zip(rows, rows[1:])]
    dur_s = (rows[-1][0] - rows[0][0]) / 1e9 if len(rows) > 1 else 0

    def sensor(col_mm, col_ok):
        ok = [r for r in rows if r[col_ok] == 1]
        vals = [r[col_mm] for r in ok if r[col_mm] >= 0]
        return {
            "rows": len(rows),
            "ok_rate": round(len(ok) / len(rows), 4) if rows else None,
            "not_ok_rows": len(rows) - len(ok),
            "nothing_in_range_rate": round((len(ok) - len(vals)) / len(ok), 4) if ok else None,
            "mm": summary(vals),
        }

    result = {
        "tool": "esp32_capture.py",
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "seconds": args.seconds,
        "reset": args.reset,
        "sent": args.send,
        "d_lines": len(rows),
        "bad_lines": bad_lines,
        "rate_hz": round((len(rows) - 1) / dur_s, 3) if dur_s else None,
        "interval_host_ms": summary(host_iv),
        "interval_esp_ms": summary(esp_iv),
        "gaps_over_2x_period": sum(1 for v in host_iv if v > 2 * REPORT_MS),
        "esp_ms_went_backwards": sum(1 for v in esp_iv if v < 0),
        "forward": sensor(2, 4),
        "down": sensor(3, 5),
        "ground_learned_mm": rows[-1][6] if rows else None,
        "E_lines": sum(1 for _, l in other if l.startswith("E ")),
        "H_lines": sum(1 for _, l in other if l.startswith("H ")),
        "info_lines": [l for _, l in other if l.startswith("I ")][:40],
        "error_lines": [l for _, l in other if l.startswith("E ")][:40],
    }
    if args.reset:
        def first(prefix):
            for t, l in other:
                if l.startswith(prefix):
                    return round((t - t_release) / 1e6, 1)
            return None
        result["boot_ms"] = {
            "banner": first("I cane_safety boot"),
            "ready": first("I ready"),
            "first_D": round((rows[0][0] - t_release) / 1e6, 1) if rows else None,
        }

    with open(args.out + ".json", "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps({k: result[k] for k in
                      ("d_lines", "rate_hz", "gaps_over_2x_period", "E_lines",
                       "H_lines")}, indent=None))
    print("info:", *result["info_lines"], sep="\n  ")
    if result["error_lines"]:
        print("errors:", *result["error_lines"], sep="\n  ")
    if args.reset:
        print("boot_ms:", result["boot_ms"])


if __name__ == "__main__":
    main()
