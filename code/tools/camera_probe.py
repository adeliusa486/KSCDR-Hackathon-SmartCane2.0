#!/usr/bin/env python3
"""Smart cane - report what the camera is REALLY doing under detect.py's settings.

detect.py asks Picamera2 for a 1280x720 main stream plus a model-sized lores
stream and lets it pick the sensor mode. Which mode it picks decides the real
field of view: on the IMX708 some modes are centre crops, and a crop makes the
true horizontal FOV narrower than the 120 deg that bearing() assumes via
--hfov. This probe uses the same configuration and prints the mode, the
ScalerCrop, the effective FOV estimate and frame timing, then saves one frame.

Keep CONFIG in step with detect.py main(). It is copied, not imported,
because detect.py builds it inline.

The camera must be free (service stopped).

    python3 camera_probe.py --frames 90 --out /tmp/cam
"""
import argparse
import json
import math
import statistics
import time

from picamera2 import Picamera2

LENS_HFOV_DEG = 120.0   # Arducam B0310 M12 lens, full sensor width


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--ev", type=float, default=0.7)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--lores", default="640x640", help="model input size")
    ap.add_argument("--frames", type=int, default=90)
    ap.add_argument("--out", required=True, help="output path prefix")
    args = ap.parse_args()
    lw, lh = map(int, args.lores.split("x"))

    picam2 = Picamera2()
    props = picam2.camera_properties
    controls = {                              # == detect.py main()
        "FrameRate": args.fps,
        "AeEnable": True,
        "AwbEnable": True,
        "ExposureValue": args.ev,
        "FrameDurationLimits": (int(1e6 / args.fps), int(1e6 / args.fps)),
        "AeExposureMode": 0,
        "NoiseReductionMode": 2,
    }
    config = picam2.create_preview_configuration(
        main={"size": (args.width, args.height), "format": "XRGB8888"},
        lores={"size": (lw, lh), "format": "RGB888"},
        controls=controls,
    )
    picam2.configure(config)
    cfg = picam2.camera_configuration()
    picam2.start()
    time.sleep(1.5)                           # same AE/AWB settle as detect.py

    metas = []
    for _ in range(args.frames):
        req = picam2.capture_request()
        metas.append(req.get_metadata())
        req.release()
    picam2.capture_file(args.out + "_main.jpg")
    picam2.stop()

    pa_w, pa_h = props["PixelArraySize"]
    crop = metas[-1].get("ScalerCrop")
    ts = [m["SensorTimestamp"] for m in metas if "SensorTimestamp" in m]
    iv = [(b - a) / 1e6 for a, b in zip(ts, ts[1:])]
    exp = [m.get("ExposureTime") for m in metas]
    gain = [m.get("AnalogueGain") for m in metas]

    # Rectilinear estimate: a crop of fraction f of the sensor width sees
    # 2*atan(f*tan(HFOV/2)). The real lens has barrel distortion, so treat
    # this as an estimate, but a big difference from 120 is real.
    eff_hfov = None
    if crop:
        f = crop[2] / pa_w
        eff_hfov = round(math.degrees(2 * math.atan(f * math.tan(math.radians(LENS_HFOV_DEG / 2)))), 1)

    result = {
        "model": props.get("Model"),
        "pixel_array": [pa_w, pa_h],
        "sensor_modes": [{"size": m["size"], "crop_limits": m.get("crop_limits"),
                          "fps": round(m["fps"], 2), "bit_depth": m["bit_depth"]}
                         for m in picam2.sensor_modes],
        "selected_sensor": {k: (list(v) if isinstance(v, tuple) else v)
                            for k, v in cfg.get("sensor", {}).items()},
        "main": {"size": list(cfg["main"]["size"]), "format": cfg["main"]["format"]},
        "lores": {"size": list(cfg["lores"]["size"]), "format": cfg["lores"]["format"]},
        "scaler_crop": list(crop) if crop else None,
        "crop_fraction_w": round(crop[2] / pa_w, 4) if crop else None,
        "crop_fraction_h": round(crop[3] / pa_h, 4) if crop else None,
        "effective_hfov_deg_estimate": eff_hfov,
        "detect_py_hfov_assumed": LENS_HFOV_DEG,
        "lores_aspect_vs_crop_aspect": [round(lw / lh, 3),
                                        round(crop[2] / crop[3], 3) if crop else None],
        "frames": len(metas),
        "frame_interval_ms": {
            "mean": round(statistics.fmean(iv), 2), "min": round(min(iv), 2),
            "max": round(max(iv), 2), "stdev": round(statistics.stdev(iv), 3),
            "over_1.5x_nominal": sum(1 for v in iv if v > 1.5 * 1000 / args.fps),
        } if len(iv) > 1 else None,
        "exposure_us": {"min": min(exp), "max": max(exp)} if all(exp) else exp[:3],
        "analogue_gain": {"min": round(min(gain), 2), "max": round(max(gain), 2)} if all(gain) else gain[:3],
        "lux_last": metas[-1].get("Lux"),
        "controls_requested": {k: (list(v) if isinstance(v, tuple) else v)
                               for k, v in controls.items()},
    }
    with open(args.out + ".json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(json.dumps({k: result[k] for k in (
        "model", "selected_sensor", "scaler_crop", "crop_fraction_w",
        "effective_hfov_deg_estimate", "frame_interval_ms", "exposure_us",
        "analogue_gain", "lux_last")}, indent=1, default=str))


if __name__ == "__main__":
    main()
