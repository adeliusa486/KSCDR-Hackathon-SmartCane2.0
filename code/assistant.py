#!/usr/bin/env python3
"""Smart cane - AI assistant on the cane's one button (ESP32 D33).

Short press   AI assistant.
              Online: says "Looking", Google Gemini describes what the camera
              sees, then the motor buzzes once and the cane listens for 5 s
              through the earbud microphone. Ask anything about the scene,
              for example "read the sign" or "what colour is the door", and it
              answers from a fresh photo. Say nothing and it stops. A press
              while it listens ends the listening early.
              Offline (no internet, or no API key): says what the cane's own
              detector sees and reads any text with Tesseract on the Pi.
Long press    Read text straight away, word for word (a short buzz at 1 s says
(1 s or more) "you can let go"). Gemini online, Tesseract offline, and
              Tesseract also when Gemini fails.
              With a Wi-Fi QR code in view (a phone's "share Wi-Fi" code), it
              saves and joins that network instead (wifi_qr.py).

Presses while it is answering are ignored. A "press" longer than 15 s is a
stuck or latched switch and is ignored too.

While the assistant works, the routine object announcements pause, so the
microphone never records the cane's own voice. Ground-hazard warnings still
speak, and the ESP32's vibration never stops.

The button is on the ESP32 (D33), which sends "K down" / "K up". This module
only times the press. The API key is read from ~/.config/smartcane/gemini_key
(chmod 600). It is never stored in the repository.

    python3 assistant.py --test-online               # is Gemini reachable?
    python3 assistant.py --test-describe photo.jpg   # one-off checks, no button
    python3 assistant.py --test-read photo.jpg
"""
import argparse
import array
import base64
import json
import math
import os
import socket
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
HOST = "generativelanguage.googleapis.com"
API = "https://" + HOST + "/v1beta/models/{}:generateContent"

LONG_PRESS_S = 1.0       # held this long = read text
STUCK_S = 15.0           # held longer = stuck or latched switch, ignored
LISTEN_S = 5.0           # follow-up question window after a description
NO_QUESTION = "NO_QUESTION"
# RAM disk on the Pi, so recordings never wear the SD card. Temp dir elsewhere.
SHM = "/dev/shm" if os.path.isdir("/dev/shm") else tempfile.gettempdir()
QUESTION_WAV = os.path.join(SHM, "cane_question.wav")

SYSTEM = (
    "You are the voice of a smart white cane used by a blind person. The photo "
    "is from a camera on the cane, pointing where they walk. Answers are read "
    "aloud by a speech synthesiser, so: plain spoken English, no lists, no "
    "symbols, no markdown, under 35 words. Say left, right or ahead and rough "
    "distance in meters. Mention anything that could trip, hit or hurt them "
    "first. Never claim something is safe to cross or walk into: say what you "
    "see and let them decide. If the photo is too dark or blurred, say so."
)
DESCRIBE = "Describe what is in front of me."
READ = ("Read out the text in the photo, word for word, most important first: "
        "signs, labels, screens, documents. Ignore the 35 word limit for this, "
        "but stop after about 80 words. If there is no readable text, say "
        "'No text found' and suggest how to point the cane.")
ASK = ("The audio clip is a question from the blind user. Answer it using the "
       "photo. If they ask you to read something, read the text word for word: "
       "ignore the 35 word limit for that, but stop after about 80 words. If "
       "the audio holds no question, only silence or noise, reply with exactly "
       f"{NO_QUESTION} and nothing else.")


def load_key(path=KEY_PATH):
    try:
        with open(path) as fh:
            # utf-8-sig drops a byte-order mark that Windows tools add.
            return fh.read().lstrip("﻿").strip()
    except OSError:
        return ""


def online(host=HOST, timeout=2.0):
    """True if the Gemini server answers a TCP connect within `timeout`.

    Without this check a cane on Wi-Fi with no internet waited for a 15 s
    timeout on each of three models before saying anything. The probe runs in
    a thread because the socket timeout does not cover the DNS lookup, which
    on a network with no upstream can hang for 5 to 20 s by itself."""
    ok = []

    def probe():
        try:
            socket.create_connection((host, 443), timeout=timeout).close()
            ok.append(True)
        except OSError:
            pass
    t = threading.Thread(target=probe, daemon=True)
    t.start()
    t.join(timeout)
    return bool(ok)


def gemini(key, prompt, jpeg=None, wav=None, context="", timeout=12,
           deadline_s=25):
    """One request to Gemini. Returns the reply text, or raises RuntimeError
    with a short reason that is safe to speak. Models are tried in order
    until one answers or deadline_s has passed."""
    t_end = time.time() + deadline_s
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
        if time.time() > t_end:
            break
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
        except urllib.error.URLError as e:
            print(f"  gemini {model}: {e!r}", file=sys.stderr)
            if isinstance(e.reason, TimeoutError):
                last = "assistant too slow, try again"   # this model, not the net
                skip.add(model)
                continue
            # The network, not the model: every other model would fail the
            # same way, so stop now instead of waiting on each in turn.
            raise RuntimeError("no internet, assistant unavailable")
        except TimeoutError as e:
            # The reply did not arrive in time: a slow or overloaded model.
            print(f"  gemini {model}: {e!r}", file=sys.stderr)
            last = "assistant too slow, try again"
            skip.add(model)
        except OSError as e:
            print(f"  gemini {model}: {e!r}", file=sys.stderr)
            raise RuntimeError("no internet, assistant unavailable")
        except Exception as e:
            # A cut-off or garbled reply (ValueError from json, an
            # http.client error): treat it as this model failing.
            print(f"  gemini {model}: {e!r}", file=sys.stderr)
            last = "assistant gave no clear answer"
            skip.add(model)
    raise RuntimeError(last)


def ocr_offline(jpeg, timeout=20):
    """Read text without internet, with Tesseract on the Pi's CPU. Rougher
    than Gemini (signs at an angle, low light), but it never needs a network.

    Returns the text (up to 80 words), "" when there is none, or None when
    Tesseract is not available."""
    path = os.path.join(SHM, "cane_ocr.jpg")
    try:
        with open(path, "wb") as fh:
            fh.write(jpeg)
        out = subprocess.run(["tesseract", path, "-", "-l", "eng", "--psm", "3"],
                             capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    # Keep lines with at least one real word, drop OCR noise like '|| ~ ;'.
    lines = [l.strip() for l in out.splitlines()
             if sum(c.isalpha() for c in l) >= 3]
    return " ".join(" ".join(lines).split()[:80])


def has_speech(wav, rate=16000, min_rms=250.0):
    """Rough check that a 16-bit mono WAV recording holds a voice, so silence
    is not sent to Gemini. Speech needs at least 4 windows of 50 ms that are
    both above min_rms and 3x louder than the recording's own noise floor, or
    at least 6 windows above 2x min_rms.

    The WAV header's length fields are not trusted (parecord may not finish
    them when it is stopped): everything after the "data" tag is audio.
    Thresholds are first values, not yet tuned on the earbud microphone.
    Gemini's NO_QUESTION reply is the second guard."""
    i = wav.find(b"data")
    if i < 0:
        return False
    pcm = wav[i + 8:]
    n = len(pcm) // 2
    win = rate // 20
    if n < 4 * win:
        return False
    samples = array.array("h")
    samples.frombytes(pcm[:n * 2])
    if sys.byteorder == "big":
        samples.byteswap()
    rms = []
    for k in range(0, n - win + 1, win):
        seg = samples[k:k + win]
        rms.append(math.sqrt(sum(s * s for s in seg) / win))
    # Two ways to count as speech: a voice rising clearly over the noise
    # floor (5th-percentile window), or sustained loud audio, which covers a
    # short clip that is speech from start to end (the user pressed the
    # button to stop as soon as they finished), where no quiet floor exists.
    floor = sorted(rms)[len(rms) // 20]
    over_floor = sum(1 for r in rms if r >= max(min_rms, 3 * floor))
    loud = sum(1 for r in rms if r >= 2 * min_rms)
    return over_floor >= 4 or loud >= 6


class EarbudMic:
    """Records from the Bluetooth earbuds' microphone.

    Earbuds play music in A2DP (good sound, no mic). The mic needs the headset
    profile, so we switch for the recording and switch back afterwards. The
    switch takes about a second, before the "speak now" buzz.
    """

    def __init__(self, mac):
        self.card = "bluez_card." + mac.replace(":", "_")
        self.proc = None

    def _pactl(self, *a):
        try:
            return subprocess.run(["pactl", *a], capture_output=True, text=True,
                                  timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            return subprocess.CompletedProcess(a, 1, "", "")

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
        try:
            os.remove(QUESTION_WAV)          # never send an old recording
        except OSError:
            pass
        self.proc = subprocess.Popen(
            ["parecord", "-d", src, "--file-format=wav", "--rate=16000",
             "--channels=1", "--format=s16le", QUESTION_WAV],
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

    snapshot():       JPEG bytes of the current view, or None.
    context():        short text of what the detector sees, for Gemini.
    speak(text):      says text and returns when done.
    cue(kind):        haptic cue, kind "listen" (speak now) or "hold" (long
                      press reached).
    local_summary():  spoken sentence of what the detector sees, for offline.
    hold_speech(on):  pause / resume the routine object announcements.
    is_online():      True if Gemini can be reached.
    """

    def __init__(self, snapshot, context, speak, bt_mac, mic=None, cue=None,
                 local_summary=None, hold_speech=None, is_online=None):
        self.snapshot = snapshot
        self.context = context
        self.speak = speak
        self.mic = mic if mic is not None else EarbudMic(bt_mac)
        self.cue = cue or (lambda kind: None)
        self.local_summary = local_summary or (lambda: "")
        self.hold_speech = hold_speech or (lambda on: None)
        self.is_online = is_online or online
        self.listen_s = LISTEN_S
        self.down_at = None
        self.hold_timer = None
        self.busy = threading.Lock()
        self.listening = threading.Event()
        self.stop_listening = threading.Event()
        import wifi_qr
        threading.Thread(target=wifi_qr.warm_up, daemon=True).start()

    # ---- button ---------------------------------------------------------

    def on_button(self, pressed):
        now = time.time()
        if pressed:
            if self.listening.is_set():
                self.stop_listening.set()      # "done talking"
                return
            if self.busy.locked():
                return                         # already answering
            if self.hold_timer is not None:    # a release was lost
                self.hold_timer.cancel()
            self.down_at = now
            self.hold_timer = threading.Timer(LONG_PRESS_S, self._long_reached)
            self.hold_timer.daemon = True
            self.hold_timer.start()
            return
        if self.down_at is None:
            return
        held, self.down_at = now - self.down_at, None
        if self.hold_timer is not None:
            self.hold_timer.cancel()
            self.hold_timer = None
        if held > STUCK_S:
            print(f"  ASSISTANT ignored a {held:.0f} s press (stuck switch?)")
            return
        self._go("read" if held >= LONG_PRESS_S else "assist")

    def _long_reached(self):
        if self.down_at is not None:
            self.cue("hold")

    def _go(self, mode):
        threading.Thread(target=self._handle, args=(mode,), daemon=True).start()

    # ---- one request ----------------------------------------------------

    def _handle(self, mode):
        if not self.busy.acquire(blocking=False):
            return
        self.hold_speech(True)
        try:
            # The internet check (up to 2 s) runs while the snapshot is taken
            # (up to 2 s), not after it.
            key = load_key()
            result = []
            probe = threading.Thread(
                target=lambda: result.append(bool(key) and self.is_online()),
                daemon=True)
            probe.start()
            jpeg = self.snapshot()
            probe.join(3.0)
            net = bool(result) and result[0]
            if jpeg is None:
                self.speak("Camera not ready")
                return
            print(f"  ASSISTANT {mode}, {'online' if net else 'offline'}")
            if mode == "read":
                if not self._wifi_code(jpeg):
                    self._read(key if net else "", jpeg)
            elif net:
                self._assist_online(key, jpeg)
            else:
                self._assist_offline(jpeg, "No internet" if key else "No assistant key")
        except Exception as e:                 # never leave the user in silence
            print(f"  ASSISTANT failed: {e!r}", file=sys.stderr)
            self.speak("Assistant error")
        finally:
            self.hold_speech(False)
            self.busy.release()

    def _ask(self, key, prompt, jpeg, wav=None):
        """Gemini with one retry when the free service is briefly busy."""
        for attempt in range(2):
            try:
                return gemini(key, prompt, jpeg, wav, self.context())
            except RuntimeError as e:
                if "busy" not in str(e) or attempt:
                    raise
                self.speak("Still looking")
                time.sleep(2)

    def _wifi_code(self, jpeg):
        """A Wi-Fi QR code in view: save and join that network, and return
        True. Otherwise False, and the long press reads text as before. A code
        that is seen but not readable gets up to 3 more photos (the user may
        still be steadying it). Without OpenCV nothing changes."""
        import wifi_qr
        found, state = wifi_qr.look(jpeg)
        for _ in range(3):
            if state != "unreadable":
                break
            more = self.snapshot()
            if more:
                found, state = wifi_qr.look(more)
        if found is None:
            if state == "unreadable":
                print("  ASSISTANT saw a QR code but could not decode it")
                self.speak("Code not readable")
            return False
        print(f"  ASSISTANT Wi-Fi code for {found['ssid']!r}")
        self.speak(f"Wi-Fi code. Network {found['ssid']}. Joining")
        self.speak(wifi_qr.join(found))
        return True

    def _read(self, key, jpeg):
        self.speak("Reading")
        reply = None
        if key:
            try:
                reply = self._ask(key, READ, jpeg)
            except RuntimeError as e:
                print(f"  ASSISTANT read online failed ({e}), reading offline")
        if reply is None:
            text = ocr_offline(jpeg)
            reply = ("Text reader not available" if text is None else
                     f"Offline reading. {text}" if text else "No text found")
        self.speak(reply)

    def _assist_online(self, key, jpeg):
        self.speak("Looking")
        t0 = time.time()
        try:
            reply = self._ask(key, DESCRIBE, jpeg)
        except RuntimeError as e:
            # Quota, a refused key, no answer: say why, then still help.
            self.speak(str(e))
            self._assist_offline(jpeg, None)
            return
        print(f"  ASSISTANT describe ({time.time() - t0:.1f}s): {reply}")
        self.speak(reply)

        wav = self._listen()
        if wav is None:
            return
        photo = self.snapshot() or jpeg       # they may have aimed at the sign
        t0 = time.time()
        try:
            answer = self._ask(key, ASK, photo, wav)
        except RuntimeError as e:
            self.speak(str(e))
            return
        print(f"  ASSISTANT answer ({time.time() - t0:.1f}s): {answer}")
        if answer.strip().upper().startswith(NO_QUESTION):
            return
        self.speak(answer)

    def _assist_offline(self, jpeg, why):
        # What the detector sees is spoken at once. Tesseract can take a few
        # seconds, so any text follows as a second sentence.
        seen = self.local_summary() or "nothing detected in front"
        self.speak((f"{why}, offline mode. " if why else "") + f"{seen}.")
        text = ocr_offline(jpeg)
        if text:
            self.speak(f"Text reads: {text}")

    def _listen(self):
        """Open the earbud mic for up to listen_s seconds. Returns WAV bytes
        when someone spoke, else None."""
        self.stop_listening.clear()
        if not self.mic.start():
            print("  ASSISTANT no microphone, not listening")
            return None
        self.listening.set()
        try:
            self.cue("listen")                 # buzz: speak now
            self.stop_listening.wait(self.listen_s)
        finally:
            self.listening.clear()
            self.mic.stop()
        try:
            with open(QUESTION_WAV, "rb") as fh:
                wav = fh.read()
        except OSError:
            return None
        if not has_speech(wav):
            print("  ASSISTANT no question heard")
            return None
        return wav


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--test-online", action="store_true",
                    help="check that the Gemini server can be reached")
    ap.add_argument("--test-describe", metavar="JPEG",
                    help="send one photo to Gemini and print the description")
    ap.add_argument("--test-read", metavar="JPEG",
                    help="read the text in one photo, offline then Gemini")
    args = ap.parse_args()
    if args.test_online:
        t0 = time.time()
        print("online" if online() else "OFFLINE", f"({time.time() - t0:.2f} s)",
              "| key", "present" if load_key() else "MISSING")
        return
    path = args.test_describe or args.test_read
    if not path:
        ap.print_help()
        return
    with open(path, "rb") as fh:
        jpeg = fh.read()
    if args.test_read:
        t0 = time.time()
        print("offline:", repr(ocr_offline(jpeg)), f"({time.time() - t0:.1f} s)")
    key = load_key()
    if not key:
        sys.exit(f"no key in {KEY_PATH}")
    t0 = time.time()
    print("gemini:", gemini(key, READ if args.test_read else DESCRIBE, jpeg),
          f"({time.time() - t0:.1f} s)")


if __name__ == "__main__":
    main()
