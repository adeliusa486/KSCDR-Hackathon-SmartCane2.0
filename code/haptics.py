#!/usr/bin/env python3
"""Smart cane - vibration alerts on GPIO18.

Speech tells the user WHAT. Vibration tells them HOW URGENT, and it arrives
first because it does not have to wait for a sentence to finish. A person can
feel "something close, on your right" in 200 ms. Saying it takes 1.5 s.

Wiring (AI HAT+ top pass-through header):

    motor VCC  -> pin 2   (5V)      or pin 1 (3V3) if the board says 3.3V only
    motor GND  -> pin 6   (GND)
    motor SIG  -> pin 12  (GPIO18)

GPIO18 is chosen because it is a hardware PWM pin, so strength can be varied
rather than only switched on and off. A far obstacle should feel different from
a car about to hit you.

THIS ASSUMES A DRIVER MODULE, not a bare motor. A bare coin motor draws far
more current than a GPIO pin can supply and will damage the pin. If your motor
has only two wires, do not use this without a transistor.

    python3 haptics.py --test          # run through every pattern
    python3 haptics.py --buzz close    # one pattern
"""
import argparse
import sys
import threading
import time

MOTOR_PIN = 18
PWM_HZ = 200  # coin motors respond well around here, and it is inaudible

# (duty %, on seconds, gap seconds, repeats)
# Tuned so urgency is FELT, not counted. The user should never have to think
# "that was three pulses, so it must be near".
#
# All duties are high on purpose. A coin motor has to overcome its own inertia
# before it spins at all, so anything under about 50% barely moves, and a
# vibration felt through a cane handle and a gloved hand needs far more energy
# than one felt against bare skin. Length is what separates the levels here,
# more than strength.
#
# The three obstacle levels escalate on ALL THREE axes at once, so the
# difference is obvious through a cane handle without the user having to
# concentrate:
#
#            strength      rhythm            total energy
#   far      gentle  60%   one short nudge   low
#   near     firm    85%   three taps        medium
#   close    maximum 100%  near-continuous   high
#
# Close is deliberately almost one unbroken buzz rather than separate pulses.
# Something about to hit you should not feel like a polite series of taps.
PATTERNS = {
    "close": (100, 0.35, 0.05, 6),   # maximum: ~2.4s of near-solid buzzing
    "near":  (85,  0.25, 0.15, 3),   # firm: three clear taps
    "far":   (60,  0.22, 0.00, 1),   # gentle: one light nudge
    "ready": (100, 0.15, 0.10, 2),   # startup confirmation
    "error": (100, 0.60, 0.25, 3),   # something is wrong
}


class Haptics:
    """Drives the motor without ever blocking the vision loop.

    A buzz already in progress is not interrupted by a lower priority one, but
    "close" always wins, because an urgent warning that waits its turn is
    useless.
    """

    PRIORITY = {"far": 0, "ready": 0, "near": 1, "error": 2, "close": 3}

    def __init__(self, pin=MOTOR_PIN, enabled=True, chip_num=None):
        self.pin = pin
        self.enabled = enabled
        self.chip = None
        self.chip_num = None
        self.lock = threading.Lock()
        self.active = None
        if not enabled:
            return
        try:
            import lgpio
            self.lgpio = lgpio
        except ImportError as e:
            print(f"haptics disabled: {e}", file=sys.stderr)
            return

        # The Pi 5 does NOT expose the 40-pin header on gpiochip0. Its GPIO
        # lives behind the RP1 south bridge, which on this unit enumerates as
        # gpiochip15 with the label "pinctrl-rp1". The number is not stable
        # across kernel versions, so find it by label rather than hard-coding
        # it. Falls back to trying every chip.
        for n in ([chip_num] if chip_num is not None else
                  self._candidates()):
            try:
                h = self.lgpio.gpiochip_open(n)
            except Exception:
                continue
            try:
                self.lgpio.gpio_claim_output(h, self.pin, 0)
                self.chip, self.chip_num = h, n
                break
            except Exception:
                try:
                    self.lgpio.gpiochip_close(h)
                except Exception:
                    pass
        if self.chip is None:
            print("haptics disabled: no gpiochip would accept "
                  f"GPIO{self.pin}", file=sys.stderr)

    @staticmethod
    def _candidates():
        """Chip numbers to try, RP1 first if we can identify it."""
        import glob
        import os
        preferred, others = [], []
        for path in sorted(glob.glob("/dev/gpiochip*")):
            try:
                n = int(path.rsplit("gpiochip", 1)[1])
            except ValueError:
                continue
            label = ""
            try:
                with open(f"/sys/bus/gpio/devices/gpiochip{n}/label") as f:
                    label = f.read().strip()
            except OSError:
                pass
            (preferred if "rp1" in label.lower() else others).append(n)
        return preferred + list(reversed(others)) or [0]

    def available(self):
        return self.chip is not None

    def _run(self, name):
        duty, on, gap, repeats = PATTERNS[name]
        try:
            for i in range(repeats):
                self.lgpio.tx_pwm(self.chip, self.pin, PWM_HZ, duty)
                time.sleep(on)
                self.lgpio.tx_pwm(self.chip, self.pin, PWM_HZ, 0)
                if gap and i < repeats - 1:
                    time.sleep(gap)
        except Exception as e:
            print(f"haptics error: {e}", file=sys.stderr)
        finally:
            try:
                self.lgpio.tx_pwm(self.chip, self.pin, PWM_HZ, 0)
            except Exception:
                pass
            with self.lock:
                self.active = None

    def buzz(self, name):
        """Fire a pattern. Returns immediately."""
        if not self.available() or name not in PATTERNS:
            return False
        with self.lock:
            if self.active is not None:
                if self.PRIORITY[name] <= self.PRIORITY[self.active]:
                    return False  # busy with something at least as urgent
            self.active = name
        threading.Thread(target=self._run, args=(name,), daemon=True).start()
        return True

    def for_distance(self, distance_word):
        """Map detect.py's distance word onto a pattern."""
        return self.buzz(distance_word if distance_word in
                         ("close", "near", "far") else "far")

    def close(self):
        if self.chip is not None:
            try:
                self.lgpio.tx_pwm(self.chip, self.pin, PWM_HZ, 0)
                self.lgpio.gpio_free(self.chip, self.pin)
                self.lgpio.gpiochip_close(self.chip)
            except Exception:
                pass
            self.chip = None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="run every pattern")
    ap.add_argument("--buzz", default="", choices=[""] + list(PATTERNS))
    ap.add_argument("--pin", type=int, default=MOTOR_PIN)
    args = ap.parse_args()

    h = Haptics(pin=args.pin)
    if not h.available():
        sys.exit("could not open GPIO. Is lgpio installed?")

    try:
        if args.buzz:
            print(f"buzzing: {args.buzz}")
            h.buzz(args.buzz)
            time.sleep(3)
        else:
            for name in ("ready", "far", "near", "close", "error"):
                duty, on, gap, reps = PATTERNS[name]
                print(f"  {name:6s}  duty {duty}%  {reps} pulse(s) of {on}s")
                h.buzz(name)
                time.sleep(reps * (on + gap) + 1.2)
        print("done")
    finally:
        h.close()


if __name__ == "__main__":
    main()
