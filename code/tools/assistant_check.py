#!/usr/bin/env python3
"""Smart cane - end-to-end check of the assistant button on the real cane.

Starts detect.py (real camera and Hailo), then "presses" the button in
software: a short press online, a long press (read text) online, and a
short press with the network treated as down. Gemini, Tesseract and the
camera snapshot are real. Speech is printed instead of spoken, the haptic
cues are printed, and the microphone is the real earbud mic if connected.

Stop the service first, the camera and the Hailo serve one program:

    systemctl --user stop smartcane
    python3 tools/assistant_check.py
    systemctl --user start smartcane
"""
import os
import re
import signal
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import assistant  # noqa: E402

MODEL = os.path.join(HERE, "models", "smartcane152_v3_h8l.hef")
LABELS = os.path.join(HERE, "models", "smartcane152.txt")
SNAP = "/dev/shm/cane_snapshot.jpg"


def main():
    proc = subprocess.Popen(
        [sys.executable, "-u", os.path.join(HERE, "detect.py"), "--all-classes",
         "--interval", "0.3", "--conf", "0.25", "--fps", "10",
         "--model", MODEL, "--labels", LABELS],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
    latest = {"body": ""}

    def reader():
        for line in proc.stdout:
            m = re.match(r"^\[\s*[\d.]+\s*fps\]\s*(.*)$", line.strip())
            if m:
                latest["body"] = m.group(1)
    threading.Thread(target=reader, daemon=True).start()

    def snapshot(timeout=3.0):
        before = os.path.getmtime(SNAP) if os.path.exists(SNAP) else 0
        proc.send_signal(signal.SIGUSR1)
        end = time.time() + timeout
        while time.time() < end:
            if os.path.exists(SNAP) and os.path.getmtime(SNAP) > before:
                with open(SNAP, "rb") as fh:
                    return fh.read()
            time.sleep(0.05)
        return None

    t_start = time.time()
    said = []

    def speak(text):
        said.append(text)
        print(f"  {time.time() - t_start:6.1f}s  SAYS: {text}", flush=True)

    def summary():
        return re.sub(r"\s*@[\d.]+", "", latest["body"]).replace("|", ".")

    try:
        for _ in range(100):                     # wait for the first report
            if latest["body"]:
                break
            time.sleep(0.2)
        print(f"detector: {latest['body'] or 'no report'}")
        results = {}
        for name, hold, net in (("short press, online", 0.15, True),
                                ("long press (read), online", 1.3, True),
                                ("short press, offline", 0.15, False)):
            said.clear()
            a = assistant.Assistant(
                snapshot, lambda: summary() or "nothing", speak,
                os.environ.get("CANE_BT_MAC", "B0:38:E2:19:DC:CC"),
                cue=lambda k: print(f"  CUE {k}", flush=True),
                local_summary=summary, is_online=(lambda n=net: n))
            a.listen_s = 3.0
            print(f"\n== {name}")
            t0 = time.time()
            a.on_button(True)
            time.sleep(hold)
            a.on_button(False)
            time.sleep(0.3)
            if not a.busy.acquire(timeout=60):
                print("  FAIL: no answer within 60 s")
                results[name] = False
                continue
            a.busy.release()
            ok = len(said) >= 1 and said[-1] not in ("Camera not ready", "Assistant error")
            results[name] = ok
            print(f"  {'OK' if ok else 'FAIL'} in {time.time() - t0:.1f} s")
        print("\nRESULT:", "PASS" if all(results.values()) else "FAIL", results)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
