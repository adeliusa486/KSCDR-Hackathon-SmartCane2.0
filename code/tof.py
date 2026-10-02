#!/usr/bin/env python3
"""Smart cane - two VL53L0X time-of-flight sensors on one I2C bus.

Both sensors power up at the same fixed address, 0x29, so they cannot share a
bus as delivered. Each one has an XSHUT pin that holds it in reset. At every
start we hold both in reset, wake them one at a time, and move each to its own
address before waking the next. The new address is volatile: it is lost on
power-off or reset, so this has to run on every boot, not once.

Wiring (AI HAT+ top pass-through header), signal pins verified by probing:

    both VIN  -> 3V3 or 5V (the breakout regulates)
    both GND  -> GND
    both SDA  -> pin 3  (GPIO2, SDA1)
    both SCL  -> pin 5  (GPIO3, SCL1)
    XSHUT A   -> pin 16 (GPIO23)   -> address 0x30
    XSHUT B   -> pin 18 (GPIO24)   -> address 0x31

Identified on the bench as VL53L0X (ID registers 0xC0..0xC2 = EE AA 10), not
VL53L1X. The L0X tops out around 1.2 m in its default mode and uses 8-bit
register addresses, so VL53L1X code will not work on it.

SINGLE-SHOT, NOT CONTINUOUS, ON PURPOSE. On this bench build continuous mode
made a sensor reset after its first reading (it fell back from 0x30 to 0x29,
which only a power cycle does), while single-shot ran clean. That points at a
sagging supply to the breakouts. Single-shot draws less average current. If a
sensor drops off anyway, read() notices and re-runs the whole bring-up, because
a ToF that silently stops reporting is the same class of bug as the Bluetooth
null sink: everything looks healthy and the user gets nothing.

Needs the venv in ~/smartcane/venv (adafruit-circuitpython-vl53l0x + blinka).

    venv/bin/python tof.py                 # live readings from both
    venv/bin/python tof.py --seconds 30
"""
import argparse
import sys
import time

# role -> XSHUT GPIO. Which physical sensor faces where is set by the mount,
# so it is a flag, not a fact baked into the code.
DEFAULT_SENSORS = {"forward": 23, "down": 24}
BASE_ADDRESS = 0x30
DEFAULT_ADDRESS = 0x29
OUT_OF_RANGE_MM = 8000  # the L0X reports 8190/8191 when it sees nothing
REINIT_EVERY = 1.0      # seconds, so a dead sensor cannot spin the CPU


class ToFPair:
    """Owns the XSHUT pins and both sensors."""

    def __init__(self, sensors=None, budget_us=33000):
        import board
        import busio
        import lgpio
        import adafruit_vl53l0x
        from haptics import Haptics

        self.lgpio = lgpio
        self.driver = adafruit_vl53l0x
        self.pins = dict(sensors or DEFAULT_SENSORS)
        self.budget_us = budget_us
        self.sensors = {}    # role -> VL53L0X
        self.addresses = {}  # role -> I2C address
        self.errors = {}     # role -> str, for sensors that failed to start
        self.ok = {}         # role -> bool, did the last read succeed
        self.reinits = 0
        self._last_reinit = 0.0

        self.chip = None
        for n in Haptics._candidates():
            try:
                h = lgpio.gpiochip_open(n)
            except Exception:
                continue
            try:
                for pin in self.pins.values():
                    lgpio.gpio_claim_output(h, pin, 0)
                self.chip = h
                break
            except Exception:
                lgpio.gpiochip_close(h)
        if self.chip is None:
            raise RuntimeError(f"no gpiochip would accept XSHUT pins {self.pins}")

        self.i2c = busio.I2C(board.SCL, board.SDA)
        self._bring_up()

    def _bring_up(self):
        """Reset every sensor, then wake and readdress them one at a time."""
        self.sensors.clear()
        self.errors.clear()
        for pin in self.pins.values():
            self.lgpio.gpio_write(self.chip, pin, 0)
        time.sleep(0.01)  # all in reset, so nothing answers at 0x29

        for i, (role, pin) in enumerate(self.pins.items()):
            addr = BASE_ADDRESS + i
            self.lgpio.gpio_write(self.chip, pin, 1)
            time.sleep(0.05)
            try:
                s = self.driver.VL53L0X(self.i2c, address=DEFAULT_ADDRESS)
                s.set_address(addr)
                s.measurement_timing_budget = self.budget_us
                self.sensors[role] = s
                self.addresses[role] = addr
                self.ok[role] = True
            except Exception as e:
                # Hold this one in reset so it cannot sit on 0x29 and collide
                # with the next sensor's bring-up.
                self.lgpio.gpio_write(self.chip, pin, 0)
                self.errors[role] = f"GPIO{pin}: {e}"
                self.ok[role] = False

    def read(self):
        """Return {role: millimetres or None}. None means nothing in range,
        or that the sensor failed this read; check self.ok to tell which."""
        out = {}
        failed = False
        for role in self.pins:
            s = self.sensors.get(role)
            if s is None:
                out[role], self.ok[role] = None, False
                failed = True
                continue
            try:
                mm = s.range
                out[role] = None if mm >= OUT_OF_RANGE_MM else mm
                self.ok[role] = True
            except Exception:
                out[role], self.ok[role] = None, False
                failed = True
        if failed and time.time() - self._last_reinit > REINIT_EVERY:
            # A sensor that reset is back at 0x29, so only a full bring-up
            # can safely readdress it.
            self._last_reinit = time.time()
            self.reinits += 1
            self._bring_up()
        return out

    def close(self):
        # Leave the sensors held in reset rather than releasing the pins, so
        # they do not wake up together and collide at 0x29.
        if self.chip is not None:
            for pin in self.pins.values():
                try:
                    self.lgpio.gpio_write(self.chip, pin, 0)
                except Exception:
                    pass
            try:
                self.lgpio.gpiochip_close(self.chip)
            except Exception:
                pass
            self.chip = None


def parse_sensors(text):
    """'forward=23,down=24' -> {'forward': 23, 'down': 24}"""
    out = {}
    for part in text.split(","):
        role, pin = part.split("=")
        out[role.strip()] = int(pin)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sensors", default="forward=23,down=24",
                    help="role=XSHUT_GPIO pairs, in address order")
    ap.add_argument("--seconds", type=float, default=15)
    ap.add_argument("--hz", type=float, default=10)
    args = ap.parse_args()

    tof = ToFPair(parse_sensors(args.sensors))
    for role, err in tof.errors.items():
        print(f"{role}: FAILED {err}", file=sys.stderr)
    for role, addr in tof.addresses.items():
        print(f"{role}: VL53L0X at 0x{addr:02x}")

    reads = errors = 0
    try:
        end = time.time() + args.seconds
        while time.time() < end:
            r = tof.read()
            reads += 1
            errors += sum(not v for v in tof.ok.values())
            print("  ".join(
                f"{k}={'ERR ' if not tof.ok[k] else '---' if v is None else f'{v:4d}mm'}"
                for k, v in r.items()), flush=True)
            time.sleep(1 / args.hz)
    finally:
        tof.close()
    print(f"{reads} reads, {errors} sensor errors, {tof.reinits} re-inits")


if __name__ == "__main__":
    main()
