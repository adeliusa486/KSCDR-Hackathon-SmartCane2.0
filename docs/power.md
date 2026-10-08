# Power

## The symptom

On the 10,000 mAh power bank the Pi's LED shows yellow (amber), then red, and the cane switches off.

## What the LED says

The Raspberry Pi 5 has one status LED with a red and a green element. Green shows activity while it runs. Red alone means power is present but the board is halted or off. Amber is both at once, which you see for a moment as the board starts. **Amber then red** means the board began to boot and then powered itself off. The Pi 5's power controller does that when its 5 V input sags too low, or when the supply cuts out under it.

On this cane none of those attempts reached the system log: every boot recorded on 7 October ended with the power button, not a crash. So the supply failed during the first seconds of boot, before Linux starts logging, which is when the Pi, the AI HAT+ and the camera all draw their start-up current together.

## Why it happens

The cane is a heavy load for a power bank. The Raspberry Pi 5 is specified for a 5 V / 5 A (27 W) USB-C supply. The Hailo-8L, camera, ESP32 and motor add to it, and the peaks come when the camera and the NPU start.

Measured on this cane:

- A UPS feeding the 5 V GPIO pin: 11 under-voltage events in 9.5 minutes, and the Hailo dropped off the PCIe bus.
- A laptop USB-C port: 2 under-voltage events in the first 90 seconds.
- A 5 V / 3 A supply after cutting the CPU to 1.8 GHz and the camera to 10 fps: one under-voltage event, 13 s after the camera and Hailo opened, none after.

The average load is well under 15 W. The failures are short dips at start-up peaks, so what matters is how well the supply **holds 5 V during a peak**, not its capacity. Typical reasons a power bank fails here:

| Cause | How to tell |
|---|---|
| USB-A port, or a USB-A to USB-C cable | USB-A ports give 5 V at 2.1 to 2.4 A and sag under load. Always use the bank's USB-C port with a USB-C to USB-C cable |
| No USB Power Delivery (PD), or only 5 V at 2 A on USB-C | The label shows only "5V 2A" or "5V 2.4A" on the output |
| Thin or long cable | A thin 1 m cable loses several tenths of a volt at 3 A. Use a short (under 50 cm) cable rated 3 A or 5 A |
| Bank nearly empty | Its voltage drops faster under load. Charge it fully before testing |
| Bank's own over-current protection | Some banks cut out on a sharp current step. The Pi then goes dark instantly |

## How to fix it

In order of cost and certainty:

1. **Check the label.** You need a USB-C output with USB PD that lists **5V⎓3A** (15 W) or more. Charge the bank fully. Use its USB-C port and a short USB-C to USB-C cable rated for 3 A or 5 A.
2. **Plug in, wait 2 minutes, then check on the Pi:**
   ```bash
   vcgencmd get_throttled            # 0x0 = no problem since boot. 0x50000 or 0x50005 = under-voltage happened
   vcgencmd pmic_read_adc EXT5V_V    # should stay at 4.9 V or above
   ```
   For a longer test: `code/tools/power_soak.sh`.
3. **If the bank only does 5 V at 3 A and still sags:** use its higher PD voltage instead. Most 20 W banks also offer 9 V at 2.22 A. A small **USB-C PD trigger board** set to 9 V (or 12 V) feeding a **5.1 V / 5 A buck converter** gives the Pi a stiff 5 V, because the bank no longer has to hold 5 V under the peak. Feed the converter's output into the Pi's USB-C port, or into 5 V pins 2 and 4 with GND pins 6 and 14, using short, thick wires.
4. **Or use a Pi 5 UPS board** with 18650 cells that is rated to deliver 5 V at 5 A.

What the software already does to lower the load: the CPU is capped at 1.8 GHz (`arm_freq=1800`), the camera runs at 10 fps, the laptop dashboard is off by default (it cost 73 % of a CPU core), and the cane service starts 8 s after boot so its peak does not land on top of the boot peak.

Leave `usb_max_current_enable` at its default until the supply is proven to hold 5 A: it raises the current the Pi allows its USB ports, which makes a weak supply worse.

## Runtime (estimate)

10,000 mAh at 3.7 V is 37 Wh. After the bank's 5 V conversion (about 85 %) roughly 31 Wh reach the cane. At 7 to 10 W that is about 3 to 4.5 hours. A USB-C power meter would turn this estimate into a measurement.

## Switching off safely

Short-press the Pi 5's power button: it shuts down cleanly. Pulling the power while the SD card is being written can corrupt it. A full image of the card exists at `backups/sd_2026-10-02.img` (not in git).
