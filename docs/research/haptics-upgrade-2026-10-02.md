# Haptics upgrade: from a coin motor to a driven LRA (2 Oct 2026)

Adeel asked for professional vibration modules. This is the plan. Nothing
here is bought or tested yet.

## What the cane has today

An ERM (eccentric rotating mass) coin motor behind a simple driver module,
switched by 200 Hz PWM from ESP32 GPIO 13 (`cane_safety.ino`). An ERM has to
spin up and spin down, so short pulses blur together and the start lags.
MEMORY.md estimates 30 to 50 ms spin-up. Never measured.

The patterns the user must tell apart (Phase 5 Step 5.7):

```text
close obstacle  continuous 100 %
near obstacle   85 %, 120 ms on / 180 ms off
far obstacle    60 %, 100 ms on / 600 ms off
ground hazard   3 x (300 ms on / 150 ms off)
```

With an ERM, "85 % vs 60 %" mostly changes speed and buzz together, and the
off gaps soften. That makes patterns harder to tell apart while walking.

## Recommended: TI DRV2605L haptic driver + LRA

- **LRA** (linear resonant actuator): a mass on a spring, driven at its
  resonance. Crisp start and stop, so pulses stay distinct.
- **DRV2605L**: the standard driver chip for ERMs and LRAs in phones and
  wearables. Closed-loop resonance tracking for LRAs, overdrive for a fast
  start, active braking for a fast stop, and a built-in effect library.
  I2C address 0x5A. Breakout boards exist (Adafruit sells one).

Starting points to buy, two of each, because the handle changes how strong a
small actuator feels:

| Part | Why |
|---|---|
| DRV2605L breakout | driver |
| 10 mm coin LRA (~175 Hz) | small, common, fits a handle |
| larger rectangular or X-axis LRA | stronger feel through a cane grip |

Check the LRA's resonant frequency and rated voltage against the DRV2605L
datasheet's LRA range before ordering.

## Smallest change first: keep the firmware, swap the driver

The DRV2605L has a PWM input mode. The existing 200 Hz PWM on GPIO 13 can
feed its IN pin, the duty cycle sets the strength, and the chip does the
closed-loop LRA driving. That keeps `safety_logic.h` and every pattern as
they are, and the Step 1.5 arbitration tests stay valid. Configuration over
I2C happens once at boot.

Wiring on the ESP32:

| DRV2605L | ESP32 |
|---|---|
| VIN | 3V3 (or 5V, check the breakout) |
| GND | GND |
| SDA / SCL | GPIO 21 / 22, shared with ToF 1 (0x29). No address clash with 0x5A |
| IN/TRIG | GPIO 13 (the current motor PWM pin) |
| motor + / - | the LRA |

Then, as a second step, move to I2C real-time playback or the effect library
if the patterns need shapes PWM cannot give (ramps, double clicks).

## How it gets tested

- Obstacle to vibration onset: measure against an external reference (Phase
  4 Step 4.2), ERM against LRA, same pattern.
- Pattern discrimination while walking, with gloves and different grips:
  a confusion matrix per pattern pair (Phase 5 Step 5.7). Pick the actuator
  by that matrix, not by feel on the bench.
- Current draw at 100 %: an LRA usually draws less than an ERM, but measure
  it for the Step 1.3 power budget.
