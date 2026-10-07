#!/usr/bin/env python3
"""Smart cane - AI assistant button (online, Google Gemini free tier).

Short press:  describe the scene in front of the cane.
Double press: read text out loud (signs, labels, letters). Falls back to
              Tesseract on the Pi when there is no internet.
Hold:         ask a question out loud. Recording runs while the button is held
              and stops on release.

Both send one camera snapshot to Gemini. A question also sends the recorded
audio, so no separate speech-to-text step is needed: Gemini hears it directly.

The button is on the ESP32 (D33), which sends "K down" / "K up". This module
only times the press. Online only, by design (Adeel, 6 Oct 2026). With no
internet it says so instead of going silent.

The API key is read from ~/.config/smartcane/gemini_key (chmod 600). It is
never stored in the repository.

    python3 assistant.py --test-describe photo.jpg   # one-off check, no button
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

KEY_PATH = os.path.expanduser("~/.config/smartcane/gemini_key")
# The "-latest" alias follows Google's current free Flash model, so the cane
# does not break when an older version is retired. The others are fallbacks
# for when it is overloaded (HTTP 503, seen on 6 Oct 2026) or renamed.
# gemini-2.5-flash is closed to new keys since then.
#
# Flash-Lite first: with minimal thinking it answered in ~6 s on the Pi,
# against 20-30 s for Flash, and someone walking cannot wait 30 s.
MODELS = ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-3.8-flash"]
FAST = {"thinkingConfig": {"thinkingLevel": "minimal"}}
API = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"

LONG_PRESS_S = 0.6
DOUBLE_PRESS_S = 0.45    # a 2nd short press within this = read text
MAX_RECORD_S = 10
# RAM disk on the Pi, so recordings never wear the SD card. Temp dir elsewhere.
SHM = "/dev/shm" if os.path.isdir("/dev/shm") else tempfile.gettempdir()
QUESTION_WAV = os.path.join(SHM, "cane_question.wav")

SYSTEM = (
    "You are the voice of a smart white cane used by a blind person. The photo "
    "is from a camera on the cane, pointing where they walk. Answers are read "
    "aloud by a speech synthesiser, so: plain spoken English, no lists, no "
    "symbols, no markdown, under 35 words. Say left, right or ahead and rough "
    "distance in steps. Mention anything that could trip, hit or hurt them "
    "first. Never claim something is safe to cross or walk into: say what you "
    "see and let them decide. If the photo is too dark or blurred, say so."
)
DESCRIBE = "Describe what is in front of me."
READ = ("Read out the text in the photo, word for word, most important first: "
        "signs, labels, screens, documents. Ignore the 35 word limit for this, "
        "but stop after about 80 words. If there is no readable text, say "
        "'No text found' and suggest how to point the cane.")
ASK = ("Answer the question in the audio clip, using the photo. If the audio "
       "is silent or unclear, say you did not catch the question.")


def load_key(path=KEY_PATH):
    try:
        with open(path) as fh:
            # utf-8-sig drops a byte-order mark that Windows tools add.
            return fh.read().lstrip("﻿").strip()
    except OSError:
        return ""


def gemini(key, prompt, jpeg=None, wav=None, context="", timeout=15):
    """One request to Gemini. Returns the reply text, or raises RuntimeError
    with a short reason that is safe to speak."""
    parts = [{"text": prompt + (f"\nThe cane's own detector currently sees: {context}."
                                if context else "")}]
    if jpeg:
        parts.append({"inline_data": {"mime_type": "image/jpeg",
                                      "data": base64.b64encode(jpeg).decode()}})
    if wav:
        parts.append({"inline_data": {"mime_type": "audio/wav",
                                      "data": base64.b64encode(wav).decode()}})
    def body(fast):
        gen = {"maxOutputTokens": 400, "temperature": 0.3}
        if fast:
            gen.update(FAST)
        return json.dumps({
            "system_instruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": gen,
        }).encode()

    last = "assistant unavailable"
    # Each model is tried with minimal thinking first. A model that does not
    # know that setting answers 400, and is then tried once without it.
    attempts = [(m, fast) for m in MODELS for fast in (True, False)]
    skip = set()
    for model, fast in attempts:
        if model in skip:
            continue
        req = urllib.request.Request(
            API.format(model), data=body(fast), method="POST",
            headers={"Content-Type": "application/json", "x-goog-api-key": key})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.load(resp)
            cands = data.get("candidates") or []
            text = " ".join(p.get("text", "") for c in cands[:1]
                            for p in c.get("content", {}).get("parts", []))
            text = text.replace("*", "").replace("#", "").strip()
            if text:
                return text
            last = "no answer came back"
        except urllib.error.HTTPError as e:
            print(f"  gemini {model} fast={fast}: HTTP {e.code}", file=sys.stderr)
            if e.code == 400 and fast:     # setting not supported, retry plain
                continue
            if e.code in (401, 403):
                raise RuntimeError("assistant key not accepted")
            # 404 retired, 429 this model's free limit, 503 overloaded:
            # all are per model, so the next model may still answer.
            last = {429: "free assistant limit reached, try again in a minute",
                    503: "assistant busy, try again"}.get(e.code, f"assistant error {e.code}")
            skip.add(model)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"  gemini {model}: {e!r}", file=sys.stderr)
            last = "no internet, assistant unavailable"
            skip.add(model)
    raise RuntimeError(last)


def ocr_offline(jpeg, timeout=20):
    """Read text without internet, with Tesseract on the Pi's CPU. Rougher
    than Gemini (signs at an angle, low light), but it never needs a network."""
    path = os.path.join(SHM, "cane_ocr.jpg")
    try:
        with open(path, "wb") as fh:
            fh.write(jpeg)
        out = subprocess.run(["tesseract", path, "-", "-l", "eng", "--psm", "3"],
                             capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return "Text reader not available"
    # Keep lines with at least one real word, drop OCR noise like '|| ~ ;'.
    lines = [l.strip() for l in out.splitlines()
             if sum(c.isalpha() for c in l) >= 3]
    text = " ".join(lines)
    if not text:
        return "No text found"
    return "Offline reading. " + " ".join(text.split()[:80])


class EarbudMic:
    """Records from the Bluetooth earbuds' microphone.

    Earbuds play music in A2DP (good sound, no mic). The mic needs the headset
    profile, so we switch for the recording and switch back afterwards. The
    switch costs about a second, which happens while the user is still talking.
    """

    def __init__(self, mac):
        self.card = "bluez_card." + mac.replace(":", "_")
        self.proc = None

    def _pactl(self, *a):
        return subprocess.run(["pactl", *a], capture_output=True, text=True,
                              timeout=5)

    def _set_profile(self, names):
        for n in names:
            if self._pactl("set-card-profile", self.card, n).returncode == 0:
                return True
        return False

    def start(self):
        if not self._set_profile(["headset-head-unit", "headset-head-unit-msbc",
                                  "handsfree_head_unit", "headset_head_unit"]):
            return False
        time.sleep(0.8)
        src = ""
        for line in self._pactl("list", "short", "sources").stdout.splitlines():
            f = line.split("\t")
            if len(f) > 1 and f[1].startswith("bluez_input"):
                src = f[1]
        if not src:
            self.stop()
            return False
        self.proc = subprocess.Popen(
            ["parecord", "-d", src, "--file-format=wav", "--rate=16000",
             "--channels=1", QUESTION_WAV],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    def stop(self):
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None
        self._set_profile(["a2dp-sink", "a2dp_sink", "a2dp-sink-sbc"])
        time.sleep(0.5)


class Assistant:
    """Glue between the button, the camera snapshot, Gemini and the speaker.

    snapshot(): returns JPEG bytes of the current view, or None.
    context():  returns a short string of what the detector sees right now.
    speak(text): says text, waiting for any current sentence to finish.
    """

    def __init__(self, snapshot, context, speak, bt_mac, mic=None):
        self.snapshot = snapshot
        self.context = context
        self.speak = speak
        self.mic = mic or EarbudMic(bt_mac)
        self.down_at = None
        self.recording = False
        self.busy = threading.Lock()
        self.timer = None
        self.pending = None      # timer waiting to see if a 2nd press follows

    def on_button(self, pressed):
        now = time.time()
        if pressed:
            if self.busy.locked():
                return                      # already answering, ignore
            self.down_at = now
            self.timer = threading.Timer(LONG_PRESS_S, self._start_recording)
            self.timer.start()
            return
        if self.down_at is None:
            return
        held = now - self.down_at
        self.down_at = None
        if self.timer:
            self.timer.cancel()
        if held >= LONG_PRESS_S:
            self._go("ask")
        elif self.pending is not None:
            # Second short press inside the window: read text.
            self.pending.cancel()
            self.pending = None
            self._go("read")
        else:
            # First short press: wait briefly in case a second one follows.
            self.pending = threading.Timer(DOUBLE_PRESS_S, self._single)
            self.pending.start()

    def on_button2(self, pressed):
        """Second button: read text on press."""
        if pressed and not self.busy.locked():
            self._go("read")

    def _single(self):
        self.pending = None
        self._go("describe")

    def _go(self, mode):
        threading.Thread(target=self._handle, args=(mode,), daemon=True).start()

    def _start_recording(self):
        if self.down_at is None:
            return
        self.recording = self.mic.start()
        print(f"  ASSISTANT recording={'yes' if self.recording else 'no mic'}")
        if self.recording:
            # Hard cap, in case the button sticks or the release is lost.
            threading.Timer(MAX_RECORD_S, self._force_release).start()

    def _force_release(self):
        if self.recording and self.down_at is not None:
            self.on_button(False)

    def _handle(self, mode):
        if not self.busy.acquire(blocking=False):
            return
        try:
            wav = None
            if mode == "ask":
                if self.recording:
                    self.mic.stop()
                    self.recording = False
                    try:
                        with open(QUESTION_WAV, "rb") as fh:
                            wav = fh.read()
                    except OSError:
                        wav = None
                if not wav or len(wav) < 16000:      # under ~0.5 s of audio
                    wav = None
                    mode = "describe"
                    self.speak("I could not hear a question, describing instead")
            self.speak("Reading" if mode == "read" else "Looking")
            jpeg = self.snapshot()
            if jpeg is None:
                self.speak("Camera not ready")
                return
            key = load_key()
            if not key and mode == "read":
                self.speak(ocr_offline(jpeg))
                return
            if not key:
                self.speak("Assistant key missing")
                return
            prompt = {"describe": DESCRIBE, "read": READ, "ask": ASK}[mode]
            t0 = time.time()
            reply = None
            for attempt in range(2):
                try:
                    reply = gemini(key, prompt, jpeg, wav, self.context())
                    break
                except RuntimeError as e:
                    reply = str(e)
                    # Free-tier overload is usually gone within seconds.
                    if "busy" not in reply or attempt:
                        break
                    self.speak("Still looking")
                    time.sleep(2)
            if mode == "read" and reply.startswith("no internet"):
                reply = ocr_offline(jpeg)
            print(f"  ASSISTANT {mode} ({time.time() - t0:.1f}s): {reply}")
            self.speak(reply)
        finally:
            self.busy.release()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--test-describe", metavar="JPEG",
                    help="send one photo to Gemini and print the description")
    ap.add_argument("--test-read", metavar="JPEG",
                    help="read the text in one photo, Gemini then offline")
    args = ap.parse_args()
    path = args.test_describe or args.test_read
    if not path:
        ap.print_help()
        return
    with open(path, "rb") as fh:
        jpeg = fh.read()
    if args.test_read:
        t0 = time.time()
        print("offline:", ocr_offline(jpeg), f"({time.time() - t0:.1f} s)")
    key = load_key()
    if not key:
        sys.exit(f"no key in {KEY_PATH}")
    t0 = time.time()
    print("gemini:", gemini(key, READ if args.test_read else DESCRIBE, jpeg),
          f"({time.time() - t0:.1f} s)")


if __name__ == "__main__":
    main()
