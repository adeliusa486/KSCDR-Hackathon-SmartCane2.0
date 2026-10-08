# Measured results

Numbers measured on this prototype, with the date and method. Nothing here is an estimate unless it says so.

## Object detection

### Model accuracy (validation set)

smartcane152_v3 on 27,906 validation images, re-run on 8 October 2026 with `code/training/val_per_class.py`:

| Metric | Value |
|---|---|
| mAP50 | 0.535 |
| mAP50-95 | 0.376 |
| Precision | 0.65 |
| Recall | 0.49 |

Per class: [objects.md](objects.md) and `results/v3_per_class.csv`. Strong classes include person (0.81), car (0.81), dog (0.84), open hole (0.82), laptop (0.82) and wet floor sign (0.96). Weak ones include curb (0.24), crosswalk (0.22), manhole (0.23), cabinet (0.23), pole (0.32) and desk (0.43). Weak classes are still announced as "obstacle" when detected with low confidence, and the ToF sensors cover poles (forward) and curbs and drops (down).

### The camera path, A/B tested on the Hailo (8 October 2026)

408 labelled street photos (2,943 objects in the walking-relevant classes), each centre-cropped to the camera's 16:9 shape and run through the cane's own Hailo-8L with `code/tools/hazard_eval.py`. "Named" means detected with the right name at the naming threshold, "noticed" means anything was detected on it (the cane then says "obstacle").

| What the model was fed | Named | Noticed |
|---|---|---|
| Original photo shape, plain resize, R,G,B (the 6 October test) | 56 % | 68 % |
| 16:9, squeezed into the square input, red and blue swapped (**the live camera path until 8 October**) | 40 % | 53 % |
| 16:9, squeezed, colours correct | 49 % | 62 % |
| 16:9, letterboxed, colours swapped | 47 % | 59 % |
| **16:9, letterboxed, colours correct (the live path since 8 October)** | **55 %** | **66 %** |
| Same, camera turned 90° and not corrected | 6 % | 13 % |

Two bugs together cost 15 points of naming. Picamera2's `RGB888` format delivers B,G,R bytes (checked against the ISP's own JPEG: correlation -1.00, and +1.00 for `BGR888`), and the 16:9 frame was squeezed 1.78x into a square while the model was trained on undistorted shapes. A sideways camera makes the model close to blind, which is why `--rotate` and `tools/vision_probe.py --orient` exist.

### Live scene

Two frames of a room (desk, office chair, backpack, paper bag) taken by the cane held in the walking position, run through both paths:

| Path | What it reported |
|---|---|
| Old | chair ahead (0.78) |
| New | chair ahead (0.82), backpack left (0.75), box left (0.74), plus two weak guesses below the naming threshold |

The desk with drawers was not named by either path: desk (recall 0.27) and cabinet (recall 0.09) are weak classes in the model itself.

### Earlier field-style test (6 October 2026)

`hazard_eval.py`, 408 validation photos, single frames, 30 ms per photo on the Hailo: named 57 %, noticed 68 %. Wet floor sign, e-scooter, dog, car, person and traffic light were noticed 80 to 95 % of the time, stairs 79 %, pothole 76 %, open hole 76 %. Pole 34 %, crosswalk 35 %, curb 35 %, rail track 35 %, bollard 39 %, barrier 42 %.

## Speed

| Measurement | Value | Date |
|---|---|---|
| Hailo inference, smartcane152_v3, per frame | 28.9 to 29.4 ms (median) | 8 Oct |
| `hailortcli benchmark`, smartcane152_v3 | 38.7 FPS | 6 Oct |
| `hailortcli benchmark`, stock yolov8s | 58.1 FPS, 13.1 ms | 19 Sep |
| Camera pipeline on the cane | 10.0 fps (set for low light and power) | 8 Oct |
| Report interval / first spoken | 0.3 s / about 0.6 to 0.9 s (3 agreeing reports) | 2 Oct |
| `detect.py` CPU | 6 to 12 % of one core, 73 % with the laptop dashboard on | 8 Oct |
| Pi temperature under load | 45 to 60 °C | 8 Oct |
| Pi boot to `systemd` ready | 5.9 to 9.4 s, varies between boots | 19 Sep, 2 Oct |
| ESP32 power-on to sensors ready / first reading | 0.40 s / 0.81 s | 8 Oct |
| ESP32 to Pi link | 20 Hz, interval P50 50.0 ms, P99 60.0 ms | 2 Oct |

## Distance sensors (VL53L0X, long-range mode)

| Measurement | Value | Date |
|---|---|---|
| ToF 1 on the bench at ~90 mm | mean 90.3 mm, stdev 1.04 mm, 1,152 samples, 0 dropouts | 2 Oct |
| ToF 2 on the bench at ~87 mm | mean 86.9 mm, stdev 1.17 mm, 400 of 400 readings | 3 Oct |
| ToF 1 at ~1.3 m (room) | 1,251 to 1,283 mm over 4 s | 8 Oct |
| ToF 2 with the cane held to walk | ground at 1,399 to 1,411 mm, learned at 1,407 mm | 8 Oct |
| Range status of 1,514 + 1,515 readings | 100 % status 11 (valid) | 8 Oct |
| Both sensor IDs | `EE AA 10`, correct | 8 Oct |

The ToF distance never reached speech in the sessions of 7 and 8 October: the serial link opened at boot and then delivered nothing for 3.5 hours and 10 hours while the ESP32 kept running and printing (its uptime proved it was never reset). The kernel logged `cp210x ttyUSB0: failed set request 0x12 status: -110`. Closing and reopening the port brought the readings straight back, so `esp32_link.py` now does that after 3 s of silence.

## Power

| Supply | Result | Date |
|---|---|---|
| UPS into the 5 V GPIO pin | 11 under-voltage events in 9.5 min, the Hailo dropped off PCIe | 2 Oct |
| Laptop USB-C port | 2 under-voltage events in the first 90 s | 3 Oct |
| 5 V / 3 A supply with 1.8 GHz cap and 10 fps | 1 under-voltage event 13 s after the service opened the camera and Hailo, none in steady state | 3 Oct |
| 10,000 mAh power bank | Pi starts, LED turns red, it shuts down before Linux logs anything | 7 Oct |

See [power.md](power.md) for the cause and the fix.
