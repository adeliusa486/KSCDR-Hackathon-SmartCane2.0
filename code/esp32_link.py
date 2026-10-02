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

Step 1.5 additions, all measured failures from Phase 1:

  * Reopen. After a USB loss the old reader never reopened the port, and the
    service stayed "ESP32 LINK SILENT" for 80 s while the ESP32 was sending
    (Step 1.2, G4). The reader now reopens on a serial error or after
    REOPEN_AFTER s with no data.
  * Repeats. Opening the port delivered 2,676 copies of two readings in 90 ms
    (Step 1.1, F5). Firmware 1.5 numbers its D lines, and a line whose number
    does not move forward is dropped, unless the ESP32 has rebooted.
  * Heartbeat. Firmware 1.5 drops Pi buzz requests and un-mutes itself when
    the Pi goes quiet for 3 s. The link sends "P" every 0.5 s, but only once
    it has seen a numbered D line, so older firmware is not flooded with
    "unknown command" errors.

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
REOPEN_AFTER = 2.0      # s with no bytes at all = reopen the port
HEARTBEAT_EVERY = 0.5   # s between "P" lines to firmware 1.5+


class Esp32Link:
    def __init__(self, port=DEFAULT_PORT, baud=115200, on_line=None,
                 on_hazard=None):
        self.port, self.baud = port, baud
        self.on_line = on_line
        self.on_hazard = on_hazard     # called as on_hazard("drop"|"step", mm)
        self.fwd_mm = None             # forward obstacle distance, None = nothing
        self.down_mm = None            # distance to the ground
        self.ground_mm = None          # learned normal ground distance
        self.fwd_ok = self.down_ok = False
        self.last_data = 0.0
        self.esp_ms = None             # ESP32 millis of the last accepted D line
        self.seq = None                # its sequence number, None = old firmware
        self.repeats_dropped = 0
        self.reopens = 0
        self._last_rx = time.time()
        self._wlock = threading.Lock()
        self._stop = False
        self.ser = None
        # Open once here so a missing port still raises to the caller, as before.
        self._open()
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()
        self._hb = threading.Thread(target=self._heartbeat, daemon=True)
        self._hb.start()

    def _open(self):
        # Default DTR/RTS handling on purpose, see the module docstring.
        ser = serial.Serial(self.port, self.baud, timeout=0.2)
        # Drop readings that piled up while the port was closed (over a
        # thousand were measured). A stale distance is worse than none.
        ser.reset_input_buffer()
        self.ser = ser
        self._last_rx = time.time()

    def _drop(self, why):
        print(f"  ESP32 link: {why}, reopening", flush=True)
        try:
            if self.ser is not None:
                self.ser.close()
        except Exception:
            pass
        self.ser = None
        self.reopens += 1

    def _reader(self):
        buf = b""
        while not self._stop:
            try:
                if self.ser is None:
                    self._open()
                    buf = b""
                # Read what is waiting, or block for ONE byte. A fixed-size
                # read(256) waits for the timeout to fill its buffer, which
                # batched readings and added up to 200 ms of lag.
                chunk = self.ser.read(self.ser.in_waiting or 1)
            except (serial.SerialException, OSError) as e:
                if self.ser is not None:
                    self._drop(f"serial error ({e})")
                time.sleep(1.0)
                continue
            if chunk:
                self._last_rx = time.time()
            elif time.time() - self._last_rx > REOPEN_AFTER:
                self._drop(f"no data for {REOPEN_AFTER:.0f} s")
                continue
            buf += chunk
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
                if self.on_line:
                    self.on_line(line)

    def _parse_data(self, line):
        parts = line.split()
        if len(parts) not in (7, 8):
            return
        try:
            ms = int(parts[1])
            seq = int(parts[7]) if len(parts) == 8 else None
            fwd, down, base = int(parts[2]), int(parts[3]), int(parts[6])
        except ValueError:
            return
        if seq is not None and self.seq is not None and seq <= self.seq:
            # A number that does not move forward is a repeat, unless the
            # ESP32 rebooted: then both its clock and its counter start low.
            rebooted = self.esp_ms is not None and ms + 1000 < self.esp_ms
            if not rebooted:
                self.repeats_dropped += 1
                return
        mm = lambda v: None if v < 0 else v
        self.fwd_mm, self.down_mm, self.ground_mm = mm(fwd), mm(down), mm(base)
        self.fwd_ok, self.down_ok = parts[4] == "1", parts[5] == "1"
        self.esp_ms, self.seq = ms, seq
        self.last_data = time.time()

    def _heartbeat(self):
        while not self._stop:
            time.sleep(HEARTBEAT_EVERY)
            if self.seq is not None and self.alive(within=1.0):
                try:
                    self.send("P")
                except Exception:
                    pass   # the reader notices a dead port and reopens it

    def alive(self, within=0.5):
        """False if the ESP32 has gone quiet, which must never be silent."""
        return time.time() - self.last_data < within

    def send(self, cmd):
        with self._wlock:
            ser = self.ser
            if ser is None:
                raise serial.SerialException("port not open")
            ser.write((cmd + "\n").encode())

    def close(self):
        self._stop = True
        self._thread.join(timeout=1)
        self._hb.join(timeout=1)
        if self.ser is not None:
            self.ser.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--send", action="append", default=[],
                    help="command to send, e.g. A0, A1, B100,500, R1, R2, S, T")
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
                  f"seq={link.seq}  "
                  f"{'' if link.alive() else 'ESP32 SILENT'}", flush=True)
            time.sleep(0.25)
        print(f"repeats dropped: {link.repeats_dropped}, reopens: {link.reopens}")
    finally:
        link.close()


if __name__ == "__main__":
    main()
