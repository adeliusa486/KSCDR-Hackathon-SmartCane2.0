# Step 1 — Connecting the Pi 5, AI HAT+ and camera

Goal of this step: a camera frame goes into the Hailo NPU and a named object
comes out, with a left/ahead/right position. Nothing else. No ToF, no vibration,
no audio yet.

---

## 1. Physical assembly (Pi powered off, cable unplugged)

Order matters. Do it in this order.

1. **Fit the active cooler first.** It sits on the CPU and its fan plugs into
   the small 4-pin JST fan header next to the USB ports. If you fit the HAT
   first you cannot reach the header.
2. **Fit the AI HAT+.** It uses **both** connectors: the 40-pin GPIO header for
   mechanical support and power, and the PCIe FPC ribbon for data. Box contains
   four threaded spacers, four long screws, four short screws, a GPIO stacking
   header and the ribbon cable.
   - Screw the four **spacers** to the Pi 5 with the **long** screws, from
     underneath.
   - Push the **GPIO stacking header** onto the Pi's 40 GPIO pins.
   - Insert the **PCIe ribbon** into the FPC connector on the Pi and on the HAT:
     lift the small latch, slide the ribbon fully in, press the latch down.
   - Lower the HAT onto the spacers and fix it with the four **short** screws.
   - The HAT should sit flat and level, not flexing.
3. **Fit the camera (Arducam B0310).**
   - The B0310 is a **Sony IMX708** sensor, 4608x2592, behind a **120 deg (H)
     M12 lens**, manual focus by turning the lens barrel. Same sensor as the
     official Raspberry Pi Camera Module 3.
   - The Pi 5 has **two camera ports, CAM0 and CAM1**, of the narrow **22-pin**
     type. The B0310 **ships with both a 15-22pin and a 15-15pin cable**, so the
     Pi 5 cable is already in the box. Use the 15-22pin one.
   - On the Pi end, the **blue stiffener faces the USB ports** and the gold
     contacts face the board. On the camera end it is the other way round.
   - Use **CAM0** and keep that choice consistent.
   - **No config.txt edit is needed.** IMX708 is natively supported in Bookworm
     and `camera_auto_detect=1` finds it. If you ever do need to force it, the
     overlay is `dtoverlay=imx708`.
   - **Focus is manual.** Autofocus controls do not apply to this M12 variant.
     Set focus once, outdoors, on something 2-4 m away, the distance band that
     matters for walking, then leave it. A lens locking ring or a dab of paint
     stops it drifting.
4. **Power.** Use a **5V / 5A (25W) USB-C supply** for bench work. Do not
   develop on the power bank. A brown-out during Hailo load looks exactly like
   a software crash and will waste hours.

Only now plug in power.

---

## 2. Flash the OS

- Raspberry Pi Imager → **Raspberry Pi OS (64-bit), Bookworm**.
- Use the **Desktop** image while developing, so you can see the camera preview.
  Switch to **Lite** later for the fast-boot build.
- In Imager's settings, set hostname, username, and enable **SSH**. You will
  mostly work over SSH.

64-bit is mandatory. The Hailo packages do not exist for 32-bit.

---

## 3. Install the software

Copy `code/setup_pi.sh` to the Pi and run it:

```bash
scp -r code pi@raspberrypi.local:~/smartcane
ssh pi@raspberrypi.local
cd ~/smartcane
chmod +x setup_pi.sh
./setup_pi.sh
```

What it does:

| Command | Why |
|---|---|
| `sudo apt update && sudo apt full-upgrade` | The Pi 5 PCIe and camera fixes ship in firmware updates |
| `sudo rpi-eeprom-update -a` | Bootloader/firmware must be recent for the HAT to enumerate |
| `sudo apt install hailo-all` | Installs the PCIe driver, HailoRT, TAPPAS core, the Python bindings and the model HEFs in one go |
| `sudo apt install python3-picamera2 rpicam-apps` | Camera stack (usually already present on Desktop images) |
| adds `dtparam=pciex1_gen=3` to `/boot/firmware/config.txt` | Runs the PCIe link at Gen3, roughly doubling NPU throughput |

Then **reboot**. The driver only loads after a reboot.

---

## 4. Verify each piece separately

Do not skip to the full pipeline. Verify in this order.

### 4a. Is the NPU alive?

```bash
hailortcli fw-control identify
```

Expect a block that includes `Device Architecture: HAILO8L` (13 TOPS) or
`HAILO8` (26 TOPS), plus firmware and serial number.

If it fails:
- `lspci | grep Hailo` — if there is no line at all, the HAT is not seated or
  the FPC ribbon is in backwards. Power off and reseat.
- `dmesg | grep -i hailo` — driver errors show up here.

**Record which architecture it prints in MEMORY.md.** This answers the open
13 vs 26 TOPS question in section 11.

### 4b. Is the camera alive?

```bash
rpicam-hello --list-cameras
```

Expect exactly one camera, reported as **`imx708`**, with modes up to
4608x2592. If it reports a different sensor, stop: the board is not the B0310
recorded in MEMORY.md, and the rest of this guide may not apply.

If the list is empty:
1. Power off, reseat both ends of the ribbon, check the contact orientation.
2. Try the other port (CAM1).
3. Only if it is still empty, force the overlay: in `/boot/firmware/config.txt`
   set `camera_auto_detect=0` and add `dtoverlay=imx708`, then reboot. This
   should not be necessary on Bookworm.

Then a 5 second preview:

```bash
rpicam-hello -t 5000
```

Use this preview to set the manual focus. Point it at something 2-4 m away and
turn the M12 lens barrel until edges look crisp, then stop touching it.

### 4c. Both together, the quick way

`rpicam-apps` ships a Hailo post-processing stage, so you can see detection
working before writing any Python:

```bash
rpicam-hello -t 0 --post-process-file /usr/share/rpi-camera-assets/hailo_yolov6_inference.json
```

Boxes drawn on the preview means the whole chain works: sensor → libcamera →
Hailo → output.

---

## 5. Our own scripts

### `check_hardware.py`

```bash
python3 check_hardware.py
```

Runs all the checks above and prints a pass/fail table, including which HEF
model files are available on the system. Run this first, every time, when
something breaks.

Note: run it with **system Python**. `picamera2` and `hailo_platform` are
installed by apt and are not on PyPI. If you want a virtual environment:

```bash
python3 -m venv --system-site-packages ~/smartcane/venv
```

### `detect.py`

```bash
python3 detect.py                 # headless, prints detections
python3 detect.py --preview       # with a window (needs a desktop session)
python3 detect.py --conf 0.5 --interval 1.0
```

It captures from the camera, runs YOLOv8s on the Hailo, and prints
cane-relevant lines, for example:

```
[ 12.3 fps ]  person ahead, close | car right, near | bicycle left, far
```

- **left / ahead / right** is a real **bearing in degrees**, not a fraction of
  frame width. This matters because of the 120 deg lens: the middle quarter of a
  120 deg frame spans about 28 deg, wide enough to call a car in the next lane
  "ahead". `--corridor 10` means anything within 10 deg of straight ahead counts
  as the walking corridor, which is about the middle 10% of the frame. Use
  `--corridor 15` if too much gets pushed to left/right.
- **close / near / far** is a rough proxy from box height. It is not a real
  distance measurement — that is the ToF sensor's job in step 2. The wide lens
  makes it pessimistic: at 120 deg things look smaller, so further away.
- The NPU is fed a square `lores` stream while the preview stays 16:9, so the
  image the model sees is horizontally squashed. That costs a little accuracy
  but does not shift the bearing, because a uniform squash preserves the
  normalised horizontal position.

---

## 6. What to measure before moving on

Write the numbers into MEMORY.md section 14.

1. FPS reported by `detect.py`, on Gen2 and on Gen3, to confirm the Gen3 gain.
2. CPU temperature under sustained load: `vcgencmd measure_temp`.
3. Whether the 6000mAh power bank survives 10 minutes of detection without
   the Pi resetting or logging an undervoltage warning
   (`dmesg | grep -i voltage`).
4. Detection quality outdoors versus indoors, for the classes that matter:
   person, car, motorcycle, bicycle, bus, dog, chair.
5. Whether the manual focus setting is sharp across 1-5 m. The 120 deg M12 lens
   has a deep depth of field, so one setting should cover the whole walking
   range, but confirm it rather than assume it.

---

## 7. Known limits of this step

- COCO's 80 classes do not include potholes, open drains, stairs, kerbs or
  Indian currency. Those all need custom-trained models later, as recorded in
  MEMORY.md section 9.
- Box height as a distance proxy is unreliable for partly visible objects.
  Real distance comes from the ToF sensor in step 2.
- No audio yet. Output is text on the terminal.
