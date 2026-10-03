#!/usr/bin/env python3
"""Smart cane - check what the vibration motor does, from the ESP32's own
report. Run ON THE PI with smartcane.service stopped (it frees the port).

    python3 haptic_check.py --seconds 45 --out /tmp/haptic

Asks the ESP32 for its status (S) every 50 ms. Each answer carries the motor
duty the firmware is writing at that moment (motor=, firmware of 3 Oct 2026
or later) and every D line carries the forward distance. Prints:

  * forward sensor: per distance band, the strongest duty seen and how much of
    the time the motor was on. Nearer should mean stronger and more often.
  * ground alarms: for each H line, the on/off pattern over the next 0.95 s (the alarm length) and
    the number of pulses. The 3 Oct firmware gives 2.

This reads what the firmware commands, not what the motor does. Whether it is
felt still needs a person holding the cane.
"""
import argparse
import re
import time

import serial


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--seconds", type=float, default=45)
    ap.add_argument("--out", required=True, help="output path prefix")
    args = ap.parse_args()

    # Plain default open: setting DTR/RTS resets a DevKit V1 (MEMORY.md 3e).
    ser = serial.Serial(args.port, 115200, timeout=0)
    time.sleep(0.1)
    ser.reset_input_buffer()
    t0 = time.monotonic()
    buf = b""
    rows = []                  # (t, kind, value...)
    fwd = None
    next_s = t0
    with open(args.out + ".log", "w") as log:
        while time.monotonic() - t0 < args.seconds:
            now = time.monotonic()
            if now >= next_s:
                ser.write(b"S\n")
                next_s += 0.05
            buf += ser.read(ser.in_waiting or 1)
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                text = raw.decode("ascii", "replace").strip()
                t = time.monotonic() - t0
                log.write(f"{t:9.3f} {text}\n")
                if text.startswith("D "):
                    f = text.split()
                    fwd = int(f[2]) if f[4] == "1" else None
                elif (m := re.search(r"motor=(\d+)", text)):
                    rows.append((t, "M", int(m.group(1)), fwd))
                elif text.startswith("H "):
                    rows.append((t, "H", text))
            time.sleep(0.002)
    ser.close()

    motor = [(t, d, mm) for t, k, *rest in rows if k == "M" for d, mm in [rest]]
    print(f"samples: {len(motor)} motor reports in {args.seconds:.0f} s")
    if not motor:
        print("no motor= field: firmware older than 3 Oct 2026, or no answer")
        return

    print("\nforward sensor (ToF 1), ground alarms excluded:")
    hazards = [t for t, k, *_ in rows if k == "H"]
    near_alarm = lambda t: any(0 <= t - h < 1.2 for h in hazards)
    bands = [(0, 400), (400, 600), (600, 800), (800, 1000), (1000, 1200),
             (1200, 1500), (1500, 99999)]
    print("  distance (mm)   samples  strongest duty  time on")
    for lo, hi in bands:
        s = [d for t, d, mm in motor if mm is not None and lo <= mm < hi and not near_alarm(t)]
        if s:
            on = sum(1 for d in s if d > 0) / len(s)
            print(f"  {lo:5d}-{hi:<6d}  {len(s):8d}  {max(s):13d} %  {on:6.0%}")
    none = [d for t, d, mm in motor if mm is None and not near_alarm(t)]
    if none:
        print(f"  nothing in range  {len(none):6d}  {max(none):13d} %")

    print("\nground alarms (ToF 2):")
    if not hazards:
        print("  none seen")
    for t, k, *rest in rows:
        if k != "H":
            continue
        seq = [d for tt, d, _ in motor if t <= tt < t + 0.95]   # 2 x 450 ms
        pulses = sum(1 for a, b in zip([0] + seq, seq) if a == 0 and b > 0)
        print(f"  {t:7.2f} s  {rest[0]}")
        print(f"           pattern (50 ms steps): {''.join('#' if d else '.' for d in seq)}")
        print(f"           pulses: {pulses}")


if __name__ == "__main__":
    main()
