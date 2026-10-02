#!/usr/bin/env python3
"""Smart cane - step 1 hardware check.

Verifies, one piece at a time, that the Pi 5 can see the AI HAT+ (Hailo) and the
camera. Run this first whenever something breaks, before debugging anything else.

    python3 check_hardware.py

Use the system Python. picamera2 and hailo_platform are installed by apt and are
not available on PyPI, so a plain venv will not see them.
"""

import glob
import os
import shutil
import subprocess
import sys

results = []


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}")
    if detail:
        for line in detail.strip().splitlines():
            print(f"       {line}")


def run(cmd, timeout=30):
    """Run a command, return (ok, combined output)."""
    if shutil.which(cmd[0]) is None:
        return False, f"{cmd[0]} is not installed or not on PATH"
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode == 0, (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, f"{' '.join(cmd)} timed out after {timeout}s"
    except Exception as exc:  # noqa: BLE001 - we want any failure reported, not raised
        return False, str(exc)


def check_os():
    arch = os.uname().machine
    ok = arch == "aarch64"
    detail = f"architecture: {arch}"
    if not ok:
        detail += "\nThe Hailo packages are 64-bit only. Reflash with the 64-bit image."
    try:
        with open("/etc/os-release") as fh:
            for line in fh:
                if line.startswith("PRETTY_NAME"):
                    detail += "\n" + line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    record("64-bit OS", ok, detail)


def check_pcie_gen():
    """PCIe Gen3 roughly doubles Hailo throughput. Warn, do not fail, if missing."""
    path = "/boot/firmware/config.txt"
    try:
        with open(path) as fh:
            text = fh.read()
    except OSError as exc:
        record("PCIe Gen3 setting", False, str(exc))
        return
    ok = "dtparam=pciex1_gen=3" in text
    detail = "dtparam=pciex1_gen=3 is set" if ok else (
        f"Not set in {path}. The NPU will run at about half speed.\n"
        "Add the line and reboot, or rerun setup_pi.sh."
    )
    record("PCIe Gen3 setting", ok, detail)


def check_hailo_pci():
    ok, out = run(["lspci"])
    if not ok:
        record("Hailo on the PCIe bus", False, out)
        return
    lines = [l for l in out.splitlines() if "hailo" in l.lower()]
    if lines:
        record("Hailo on the PCIe bus", True, "\n".join(lines))
    else:
        record(
            "Hailo on the PCIe bus",
            False,
            "No Hailo device in lspci.\n"
            "Power off and reseat the AI HAT+ ribbon; check the contact orientation.\n"
            "Then check: dmesg | grep -i hailo",
        )


def check_hailo_fw():
    ok, out = run(["hailortcli", "fw-control", "identify"])
    detail = out
    if ok:
        arch = [l for l in out.splitlines() if "Architecture" in l]
        if arch:
            detail = out + "\n>>> Record this architecture line in MEMORY.md."
    record("Hailo firmware responds", ok, detail)


def check_hefs():
    hefs = sorted(glob.glob("/usr/share/hailo-models/*.hef"))
    if hefs:
        record(
            "Model files (.hef) present",
            True,
            "\n".join(os.path.basename(h) for h in hefs),
        )
    else:
        record(
            "Model files (.hef) present",
            False,
            "Nothing in /usr/share/hailo-models/. Install with: sudo apt install hailo-all",
        )


def check_camera():
    ok, out = run(["rpicam-hello", "--list-cameras"], timeout=20)
    listed = ok and "Available cameras" in out and "No cameras available" not in out
    detail = out
    if listed:
        # The Arducam B0310 carries a Sony IMX708. Anything else means the
        # hardware does not match what MEMORY.md records, and the --hfov
        # default in detect.py (120 deg) is then wrong too.
        if "imx708" in out.lower():
            detail = out + "\n>>> imx708, as expected for the Arducam B0310."
        else:
            detail = out + (
                "\n>>> WARNING: expected imx708 (Arducam B0310), found something else."
                "\n    Check which camera is connected, update MEMORY.md, and pass"
                "\n    the correct --hfov to detect.py."
            )
    elif ok:
        detail = out + (
            "\nCommand ran but found no camera.\n"
            "Reseat both ends of the ribbon (blue stiffener towards the USB ports "
            "on the Pi end), try CAM1, and check you are using the 15-22pin cable "
            "that came in the B0310 box, not the 15-15pin one."
        )
    record("Camera detected by libcamera", listed, detail)


def check_python_modules():
    for mod, hint in (
        ("picamera2", "sudo apt install python3-picamera2"),
        ("hailo_platform", "sudo apt install hailo-all"),
        ("cv2", "sudo apt install python3-opencv  (only needed for --preview)"),
        ("numpy", "sudo apt install python3-numpy"),
    ):
        try:
            __import__(mod)
            record(f"python module: {mod}", True)
        except ImportError as exc:
            record(
                f"python module: {mod}",
                False,
                f"{exc}\nInstall with: {hint}\n"
                "If you are in a venv, recreate it with --system-site-packages.",
            )


def check_picamera2_hailo_helper():
    """Picamera2 ships a Hailo helper class; detect.py prefers it when present."""
    try:
        from picamera2.devices import Hailo  # noqa: F401
        record("picamera2 Hailo helper", True, "picamera2.devices.Hailo is available")
    except Exception as exc:  # noqa: BLE001
        record(
            "picamera2 Hailo helper",
            False,
            f"{exc}\nNot fatal. detect.py falls back to the raw hailo_platform API.",
        )


def check_thermals():
    ok, out = run(["vcgencmd", "measure_temp"])
    record("CPU temperature readable", ok, out)
    ok2, out2 = run(["vcgencmd", "get_throttled"])
    if ok2:
        detail = out2
        if "throttled=0x0" not in out2:
            detail += "\nNon-zero means throttling or undervoltage has occurred.\n" \
                      "Use a 5V/5A supply, not the power bank, for bench work."
        record("No throttling / undervoltage flags", "throttled=0x0" in out2, detail)


def main():
    print("Smart cane - step 1 hardware check\n" + "=" * 42)
    check_os()
    check_pcie_gen()
    check_hailo_pci()
    check_hailo_fw()
    check_hefs()
    check_camera()
    check_python_modules()
    check_picamera2_hailo_helper()
    check_thermals()

    failed = [n for n, ok, _ in results if not ok]
    print("\n" + "=" * 42)
    print(f"{len(results) - len(failed)} passed, {len(failed)} failed")
    if failed:
        print("Failed checks:")
        for n in failed:
            print(f"  - {n}")
        print("\nFix these top to bottom. Later checks depend on earlier ones.")
        return 1
    print("Everything is up. Next: python3 detect.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
