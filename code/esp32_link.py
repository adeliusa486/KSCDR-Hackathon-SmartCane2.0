#!/usr/bin/env python3
"""Smart cane - Pi side of the USB serial link to the ESP32 safety co-processor.

The ESP32 (code/esp32/cane_safety) owns the two ToF sensors and the vibration
motor and buzzes on its own. One sensor looks forward (obstacle distance), the
other looks down at the ground (holes, drains, steps). This module listens so
the Pi can add speech, and can send a few commands.

The port must open WITHOUT resetting the ESP32, or the safety loop goes dark
every time the Pi software restarts. On a DevKit V1, DTR/RTS drive EN and GPIO0
through a two-transistor circuit that pulls EN low only when RTS is asserted
and DTR is not. Linux asserts both on open, which is harmless. Setting
dtr=False then rts=False before open (the usual advice) passes through exactly
the reset state between the two writes. Measured: that reset the ESP32 on every
open, while the plain default open reset it 0 times in 3.

    python3 esp32_link.py                     # print readings for 10 s
    python3 esp32_link.py --seconds 30
    python3 esp32_link.py --send B100,500     # one buzz, then print
    python3 esp32_link.py --send R2           # swap forward/down roles (saved)
"""
import argparse
import threading
import time

import serial

DEFAULT_PORT = "/dev/ttyUSB0"


class Esp32Link:
    def __init__(self, port=DEFAULT_PORT, baud=115200, on_line=None,
                 on_hazard=None):
        # Default DTR/RTS handling on purpose, see the module docstring.
        self.ser = serial.Serial(port, baud, timeout=0.2)
        # Drop readings that piled up while the port was closed (over a
        # thousand were measured). A stale distance is worse than none.
        self.ser.reset_input_buffer()
        self.on_line = on_line
        self.on_hazard = on_hazard     # called as on_hazard("drop"|"step", mm)
        self.on_button = None          # called as on_button(pressed: bool)
        self.on_button2 = None         # second button (D32), same signature
        self.fwd_mm = None             # forward obstacle distance, None = nothing
        self.down_mm = None            # distance to the ground
        self.ground_mm = None          # learned normal ground distance
        self.fwd_ok = self.down_ok = False
        self.last_data = 0.0
        self._stop = False
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self):
        buf = b""
        while not self._stop:
            try:
                # Read what is waiting, or block for ONE byte. A fixed-size
                # read(256) waits for the timeout to fill its buffer, which
                # batched readings and added up to 200 ms of lag.
                buf += self.ser.read(self.ser.in_waiting or 1)
            except serial.SerialException:
                time.sleep(0.5)
                continue
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                line = raw.decode(errors="replace").strip()
                if line.startswith("D "):
                    self._parse_data(line)
                elif line.startswith("H ") and self.on_hazard:
                    parts = line.split()
                    if len(parts) >= 3:
                        try:
                            self.on_hazard(parts[1], int(parts[2]))
                        except Exception as e:
                            print(f"hazard callback failed: {e}")
                elif line in ("K down", "K up", "J down", "J up"):
                    print(f"  BUTTON {line}")
                    cb = self.on_button if line[0] == "K" else self.on_button2
                    if cb:
                        try:
                            cb(line.endswith("down"))
                        except Exception as e:
                            print(f"button callback failed: {e}")
                if self.on_line:
                    self.on_line(line)

    def _parse_data(self, line):
        try:
            _, _ms, fwd, down, fok, dok, base = line.split()
            mm = lambda v: None if int(v) < 0 else int(v)
            self.fwd_mm, self.down_mm, self.ground_mm = mm(fwd), mm(down), mm(base)
            self.fwd_ok, self.down_ok = fok == "1", dok == "1"
            self.last_data = time.time()
        except ValueError:
            pass

    def alive(self, within=0.5):
        """False if the ESP32 has gone quiet, which must never be silent."""
        return time.time() - self.last_data < within

    def send(self, cmd):
        self.ser.write((cmd + "\n").encode())

    def close(self):
        self._stop = True
        self._thread.join(timeout=1)
        self.ser.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--send", action="append", default=[],
                    help="command to send, e.g. A0, A1, B100,500, R1, R2, S")
    args = ap.parse_args()

    link = Esp32Link(args.port,
                     on_line=lambda l: None if l.startswith("D ") else print(l, flush=True))
    try:
        time.sleep(0.3)
        for c in args.send:
            link.send(c)
            time.sleep(0.2)
        end = time.time() + args.seconds
        fmt = lambda v, ok: "ERR " if not ok else "--- " if v is None else f"{v:4d}mm"
        while time.time() < end:
            print(f"forward={fmt(link.fwd_mm, link.fwd_ok)}  "
                  f"down={fmt(link.down_mm, link.down_ok)}  "
                  f"ground={link.ground_mm if link.ground_mm else 'learning'}  "
                  f"{'' if link.alive() else 'ESP32 SILENT'}", flush=True)
            time.sleep(0.25)
    finally:
        link.close()


if __name__ == "__main__":
    main()
