#!/usr/bin/env python3
"""Tests for esp32_link.py, run on Linux (WSL or the Pi). Needs pyserial.

    python3 code/tests/test_esp32_link.py

Parsing tests feed lines straight into _parse_data. The reopen test runs the
real reader thread against a pseudo-terminal, goes quiet for longer than
REOPEN_AFTER, and checks that the link reopens and data flows again.
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import esp32_link  # noqa: E402
from esp32_link import Esp32Link  # noqa: E402

failures = 0


def check(cond, msg):
    global failures
    if not cond:
        failures += 1
        print(f"FAIL: {msg}")


def bare_link():
    """An Esp32Link with its state but no port and no threads."""
    link = Esp32Link.__new__(Esp32Link)
    link.fwd_mm = link.down_mm = link.ground_mm = None
    link.fwd_ok = link.down_ok = False
    link.last_data = 0.0
    link.esp_ms = link.seq = None
    link.repeats_dropped = 0
    return link


def test_old_firmware_lines():
    link = bare_link()
    link._parse_data("D 1000 450 120 1 1 118")
    check(link.fwd_mm == 450 and link.down_mm == 120 and link.ground_mm == 118,
          "7-field line from pre-1.5 firmware is parsed")
    check(link.seq is None, "old firmware has no sequence number")
    link._parse_data("D 1050 -1 120 1 0 -1")
    check(link.fwd_mm is None and link.down_ok is False and link.ground_mm is None,
          "-1 means nothing in range / not learned")


def test_repeats_dropped():
    # The Step 1.1 F5 burst: thousands of copies of the same reading, then a
    # reading that goes back in time.
    link = bare_link()
    link._parse_data("D 2092145 91 -1 1 0 -1 100")
    for _ in range(1000):
        link._parse_data("D 2092145 91 -1 1 0 -1 100")
    link._parse_data("D 2092195 92 -1 1 0 -1 101")
    for _ in range(1000):
        link._parse_data("D 2092195 92 -1 1 0 -1 101")
    link._parse_data("D 2092145 55 -1 1 0 -1 100")   # stale, back in time
    check(link.repeats_dropped == 2001, f"repeats dropped ({link.repeats_dropped})")
    check(link.fwd_mm == 92 and link.seq == 101, "stale reading did not win")
    link._parse_data("D 2092245 93 -1 1 0 -1 102")
    check(link.fwd_mm == 93, "stream continues after the burst")


def test_reboot_accepted():
    link = bare_link()
    link._parse_data("D 900000 300 -1 1 0 -1 18000")
    link._parse_data("D 900 1200 -1 1 0 -1 0")       # ESP32 rebooted
    check(link.seq == 0 and link.fwd_mm == 1200, "reading after an ESP32 reboot accepted")


def test_garbage_ignored():
    link = bare_link()
    link._parse_data("D 1000 450 120 1 1 118 7")
    for bad in ("D 1000 abc 120 1 1 118 8", "D 1000", "D 1 2 3 4 5 6 7 8 9"):
        link._parse_data(bad)
    check(link.fwd_mm == 450 and link.seq == 7, "malformed lines change nothing")


def test_reopen_after_silence():
    master, slave = os.openpty()
    path = os.ttyname(slave)
    esp32_link.REOPEN_AFTER = 1.0
    link = Esp32Link(path)
    stop = threading.Event()
    seq = [0]

    def writer(seconds):
        end = time.time() + seconds
        while time.time() < end and not stop.is_set():
            os.write(master, f"D {seq[0] * 50} 400 100 1 1 99 {seq[0]}\n".encode())
            seq[0] += 1
            time.sleep(0.05)

    try:
        writer(1.0)
        check(link.alive(), "data flows before the silence")
        time.sleep(2.0)                     # longer than REOPEN_AFTER
        check(not link.alive(), "link reports silence")
        check(link.reopens >= 1, f"reader reopened the port ({link.reopens})")
        writer(1.0)
        check(link.alive(), "data flows again after the reopen")
        check(link.seq == seq[0] - 1, f"latest reading accepted (seq {link.seq})")
    finally:
        stop.set()
        link.close()
        os.close(master)
        os.close(slave)


if __name__ == "__main__":
    test_old_firmware_lines()
    test_repeats_dropped()
    test_reboot_accepted()
    test_garbage_ignored()
    test_reopen_after_silence()
    if failures:
        print(f"{failures} check(s) failed")
        sys.exit(1)
    print("all esp32_link checks passed")
