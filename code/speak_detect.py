#!/usr/bin/env python3
"""Smart cane - speak what the camera sees.

Wraps detect.py, reads its printed reports, and speaks them through the
default audio sink (Bluetooth headset while developing, wired bone-conduction
headset in the product).

Runs detect.py as a subprocess so the vision path and the speech path can be
tested and replaced independently. The only coupling is SIGUSR1, which asks
detect.py for a camera snapshot for the AI assistant (assistant.py).

Four things matter more than the words themselves:

  1. Do not repeat. A cane that says "person ahead" thirty times a second is
     unusable. Each phrase is muted for --repeat seconds after it is spoken.
  2. Do not queue. If speech is still playing, new reports are dropped rather
     than stacked, or the user hears warnings about obstacles they already
     walked past.
  3. Never speak into a black hole. Bluetooth earbuds sleep when idle. When
     they drop, PulseAudio silently falls back to a null sink and everything
     is swallowed with no error at all. We check the sink before every phrase
     and reconnect when it is dead. This was a real failure in testing: the
     log said SPEAKING for minutes while the user heard nothing.
  4. Never block forever. espeak-ng and paplay both get hard timeouts. A
     hung paplay against a half-dead Bluetooth link would otherwise hold the
     speech lock forever and the cane would go permanently silent while still
     appearing healthy.

    python3 speak_detect.py --interval 1.5
"""
import argparse
import math
import os
import re
import signal
import struct
import subprocess
import sys
import threading
import time
import wave

HERE = os.path.dirname(os.path.abspath(__file__))

# detect.py prints lines like:
#   [ 30.0 fps]  person ahead, close | car left, far
REPORT = re.compile(r"^\[\s*[\d.]+\s*fps\]\s*(.*)$")

# Things worth interrupting someone's day for, most urgent first. Anything not
# in this list is still spoken, just ranked below these.
PRIORITY = [
    # drop-offs and holes first: a fall is the worst outcome
    "open hole", "stairs", "pothole", "manhole", "curb", "rail track",
    "car", "bus", "truck", "van", "taxi", "motorcycle", "train", "bicycle",
    "e-scooter", "cyclist", "motorcyclist",
    "person", "child", "dog", "cow", "horse",
    "traffic cone", "barrier", "bollard", "pole", "utility pole",
    "traffic light", "pedestrian signal", "crosswalk", "stop sign",
    "fire hydrant", "bench",
]

# COCO classes a walking person can actually be harmed by or needs to find.
# Everything else in the 80 is indoor clutter that only adds false alarms:
# toothbrush, hair drier, teddy bear, spoon, and so on. Used unless
# --no-filter is passed.
RELEVANT = {
    # things that move and can hit you
    "person", "bicycle", "car", "motorcycle", "bus", "train", "truck",
    "boat", "airplane",
    # animals on Indian streets
    "dog", "cat", "cow", "horse", "sheep", "bird",
    # street furniture and navigation landmarks
    "traffic light", "stop sign", "fire hydrant", "parking meter", "bench",
    "chair", "couch", "bed", "dining table", "toilet", "tv", "refrigerator",
    # carried objects worth finding
    "backpack", "handbag", "suitcase", "umbrella", "bottle", "cup",
    "cell phone", "laptop", "book", "clock",
    # smartcane152 model (6 Oct 2026): the street hazards and landmarks it
    # was trained for. Without these they would all be called "obstacle".
    "child", "cyclist", "motorcyclist", "wheelchair", "stroller", "goat",
    "camel", "van", "taxi", "ambulance", "e-scooter", "skateboard",
    "golf cart", "shopping cart", "trailer",
    "pedestrian signal", "crosswalk button", "traffic sign", "crosswalk",
    "street light", "utility pole", "pole", "yield sign", "do not enter sign",
    "one way sign", "pedestrian crossing sign", "speed limit sign",
    "construction sign", "sidewalk closed sign", "bus stop sign", "exit sign",
    "wet floor sign", "trash can", "bike rack", "mailbox", "utility box",
    "fountain", "potted plant", "barrel", "traffic cone", "bollard",
    "sidewalk sign", "kiosk", "barrier", "fence", "ladder", "tent", "pillar",
    "curb", "curb ramp", "stairs", "escalator", "ramp", "pothole", "manhole",
    "storm drain", "sidewalk crack", "speed bump", "rail track",
    "tactile paving", "open hole", "swimming pool",
    "door", "elevator", "atm", "tree", "palm tree", "table", "desk",
    "stool", "cabinet", "box", "plastic bag", "glasses", "keyboard", "mouse",
    "remote", "knife",
}

# A sink named like this means PulseAudio has no real output device and is
# throwing audio away.
DEAD_SINKS = ("auto_null", "@DEFAULT_SINK@", "")


def rank(phrase):
    """Lower is more urgent."""
    for i, p in enumerate(PRIORITY):
        if phrase.startswith(p):
            return i
    return len(PRIORITY)


def split_phrase(phrase):
    """'person left, close @0.87' -> ('person', 'left', 'close', 0.87)."""
    score = 0.0
    if "@" in phrase:
        phrase, _, raw = phrase.rpartition("@")
        try:
            score = float(raw)
        except ValueError:
            pass
    head, _, dist = phrase.partition(",")
    head = head.strip()
    dist = dist.strip()
    for direction in ("ahead", "left", "right"):
        if head.endswith(" " + direction):
            return head[: -len(direction) - 1].strip(), direction, dist, score
    return head, "", dist, score


def class_of(phrase):
    """'person left, close' -> 'person'. Handles two-word classes."""
    return split_phrase(phrase)[0]


def spoken_distance(mm):
    """Measured ToF distance in metres, 0.1 m steps (the ToF is +-3 cm):
    1240 -> '1.2 meters', 640 -> '0.6 meters', 999 -> '1 meter'."""
    m = max(0.1, round(mm / 1000.0, 1))
    return "1 meter" if m == 1.0 else f"{m:g} meters"


def camera_distance(m):
    """Camera estimate in metres. It is only good to about +-30 %, so half
    metre steps and 'about': 2.4 -> 'about 2.5 meters'."""
    m = max(0.5, round(m * 2) / 2.0)
    return "about 1 meter" if m == 1.0 else f"about {m:g} meters"


def parse_dist(dist):
    """detect.py's distance field: 'near 2.4m' -> ('near', 2.4),
    'close' -> ('close', None)."""
    parts = dist.split()
    if parts and parts[-1].endswith("m"):
        try:
            return " ".join(parts[:-1]), float(parts[-1][:-1])
        except ValueError:
            pass
    return dist, None


def distance_band(mm):
    """Coarse band used to decide whether a changed distance is worth saying
    again. Re-announcing every 10 cm would never let the user hear anything
    else, but 'it just got close' must not be muted by the repeat timer."""
    return ("very close" if mm < 500 else "close" if mm < 1000
            else "near" if mm < 2500 else "far")


def tof_measures(phrase, fwd_mm):
    """True if the forward ToF reading belongs to this object.

    Only 'ahead' can get it. The VL53L0X sees a ~25 degree cone, roughly the
    camera's ahead corridor, so a left or right object is not what the ToF is
    measuring. And when the camera's own estimate disagrees by more than 2x,
    the beam is on something else (a chair in front of the person the camera
    named), so the reading is not given to the named object either.
    """
    if fwd_mm is None:
        return False
    _, direction, dist, _ = split_phrase(phrase)
    if direction != "ahead":
        return False
    est = parse_dist(dist)[1]
    return est is None or 0.5 <= (fwd_mm / 1000.0) / est <= 2.0


def with_tof(phrases, fwd_mm):
    """Spoken form of each phrase, with the best distance there is:
    the measured ToF distance when it belongs to the object, else the
    camera's estimate in metres, else the camera's size word.

    Returns (spoken phrases, repeat keys). The key carries a distance band, not
    the exact number, so 'person ahead' approaching from 1.1 m to 0.4 m is said
    again while 1.1 m to 1.0 m is not.
    """
    spoken, keys = [], []
    for p in phrases:
        cls, direction, dist, _ = split_phrase(p)
        word, est = parse_dist(dist)
        head = f"{cls} {direction}" if direction else cls
        if tof_measures(p, fwd_mm):
            spoken.append(f"{head}, {spoken_distance(fwd_mm)}")
            keys.append(f"{head} {distance_band(fwd_mm)}")
        elif est is not None:
            spoken.append(f"{head}, {camera_distance(est)}")
            keys.append(f"{head} {distance_band(est * 1000)}")
        else:
            spoken.append(f"{head}, {word}" if word else head)
            keys.append(f"{head} {word}")
    return spoken, keys


def resolve(phrases, relevant, name_conf):
    """Decide, per detection, whether to say its name or call it an obstacle.

    This is how the cane gets high recall and trustworthy names at the same
    time, which otherwise pull in opposite directions:

        detector runs at a LOW threshold    -> almost nothing is missed
        naming needs a HIGH confidence      -> names are trustworthy
        everything in between becomes       -> "obstacle <direction>"

    So a faint, uncertain blob is never silently dropped. The user is told
    something is in their way, just not told a name we do not believe. A wrong
    name erodes trust in the device. "Obstacle" never does.

    Multiple unknowns in the same direction collapse into one, otherwise a
    cluttered pavement produces "obstacle left. obstacle left. obstacle left".
    """
    out = []
    seen_obstacle = set()
    for p in phrases:
        cls, direction, dist, score = split_phrase(p)
        named = cls in relevant and score >= name_conf
        if named:
            out.append(f"{cls} {direction}, {dist}" if direction
                       else f"{cls}, {dist}")
            continue
        key = (direction, dist)
        if key in seen_obstacle:
            continue
        seen_obstacle.add(key)
        out.append(f"obstacle {direction}, {dist}" if direction else
                   f"obstacle, {dist}")
    return out


def pick_fresh(phrases, spoken, keys, fresh, limit):
    """The objects to say now: most urgent first, skipping any whose own
    repeat timer is still running and any sentence already picked (two
    people both 'right, close' are said once). Returns (phrase, spoken, key)
    triples. Before 8 Oct 2026 the whole sentence shared one timer, so the
    same top two objects blocked everything else in view."""
    picked, seen = [], set()
    for p, s, k in zip(phrases, spoken, keys):
        if s in seen or not fresh(k):
            continue
        seen.add(s)
        picked.append((p, s, k))
        if len(picked) == limit:
            break
    return picked


class Confirmer:
    """Suppresses one-frame flickers.

    A single frame of YOLO calling a shadow a 'dog' is normal and harmless.
    Speaking it is not. A class must be seen in `need` consecutive reports
    before it is allowed through, which removes almost all spurious labels at
    the cost of one report of latency (about 1.5 s at default interval).

    Misses are forgiven once, so an object that flickers out for a single
    frame does not have to earn its place again from zero.
    """

    def __init__(self, need):
        self.need = need
        self.streak = {}
        self.grace = {}

    def update(self, phrases):
        seen = {class_of(p) for p in phrases}
        for cls in list(self.streak):
            if cls not in seen:
                if self.grace.get(cls, 0) > 0:
                    self.grace[cls] -= 1
                else:
                    del self.streak[cls]
                    self.grace.pop(cls, None)
        for cls in seen:
            self.streak[cls] = self.streak.get(cls, 0) + 1
            self.grace[cls] = 1
        return [p for p in phrases if self.streak.get(class_of(p), 0) >= self.need]


def run(cmd, timeout):
    """Run a command with a hard timeout. Returns True on success."""
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
        return True
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT after {timeout}s: {' '.join(cmd[:2])}", file=sys.stderr)
        return False
    except subprocess.CalledProcessError:
        return False
    except FileNotFoundError:
        print(f"  missing command: {cmd[0]}", file=sys.stderr)
        return False


class AudioLink:
    """Knows whether sound can actually reach the user, and fixes it if not."""

    def __init__(self, mac, retry_every, verbose):
        self.mac = mac
        self.retry_every = retry_every
        self.verbose = verbose
        self.last_attempt = 0.0
        self.was_alive = None

    def current_sink(self):
        try:
            out = subprocess.run(["pactl", "info"], capture_output=True,
                                 text=True, timeout=5).stdout
            for line in out.splitlines():
                if line.startswith("Default Sink:"):
                    return line.split(":", 1)[1].strip()
        except Exception:
            pass
        return ""

    def alive(self):
        """True if there is a real output device, not a null sink."""
        sink = self.current_sink()
        ok = sink not in DEAD_SINKS and not sink.startswith("auto_null")
        if ok != self.was_alive:
            if ok:
                print(f"  AUDIO OK: {sink}")
            else:
                print(f"  AUDIO DEAD: default sink is '{sink}' - nothing "
                      f"can be heard", file=sys.stderr)
            self.was_alive = ok
        return ok

    def try_reconnect(self):
        """Throttled attempt to bring the Bluetooth headset back."""
        if not self.mac:
            return
        now = time.time()
        if now - self.last_attempt < self.retry_every:
            return
        self.last_attempt = now
        print(f"  reconnecting {self.mac} ...")
        run(["bluetoothctl", "connect", self.mac], timeout=15)
        time.sleep(2)
        sink = self.current_sink()
        if sink and not sink.startswith("auto_null"):
            # Make the freshly connected headset the default again.
            run(["pactl", "set-default-sink", sink], timeout=5)
            print(f"  reconnected, sink is {sink}")

    def keepalive(self, path):
        """Near-silent blip so idle earbuds do not fall asleep."""
        if not os.path.exists(path):
            sr = 44100
            f = wave.open(path, "w")
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(sr)
            frames = [struct.pack("<h", int(2 * math.sin(2 * math.pi * 440 * i / sr)))
                      for i in range(int(sr * 0.3))]
            f.writeframes(b"".join(frames))
            f.close()
        run(["paplay", path], timeout=8)


class Speaker:
    """Speaks phrases, never overlapping, never repeating too soon."""

    def __init__(self, voice, speed, repeat_after, link, verbose,
                 dry_run=False):
        self.dry_run = dry_run
        self.voice = voice
        self.speed = speed
        self.repeat_after = repeat_after
        self.link = link
        self.verbose = verbose
        self.busy = threading.Lock()
        self.last_said = {}
        self.last_sound = time.time()
        self.on_speak = None     # demo dashboard: called as on_speak(text, kind)

    def _note(self, text, kind="speech"):
        if self.on_speak is not None:
            try:
                self.on_speak(text, kind)
            except Exception:
                pass

    def _play(self, text, on_start=None):
        try:
            wav = "/tmp/cane_speech.wav"
            if run(["espeak-ng", "-v", self.voice, "-s", str(self.speed),
                    "-w", wav, text], timeout=10):
                # Fire the sync buzz only now, after synthesis, so the user
                # feels it as the words begin rather than ~150 ms before.
                if on_start is not None:
                    try:
                        on_start()
                    except Exception as e:
                        print(f"  on_start failed: {e}", file=sys.stderr)
                # 30 s, not 15: an assistant answer runs up to ~15 s of speech.
                if run(["paplay", wav], timeout=30):
                    self.last_sound = time.time()
        finally:
            # Always release, whatever happened. A stuck lock here would make
            # the cane silent forever while still looking healthy.
            self.busy.release()

    def fresh(self, key, repeat_after=None):
        """True if `key` has not been spoken within the repeat time."""
        repeat_after = self.repeat_after if repeat_after is None else repeat_after
        return time.time() - self.last_said.get(key, 0) >= repeat_after

    def say(self, text, key=None, urgent=False, repeat_after=None,
            on_start=None, part_keys=None):
        """key: what the repeat timer is keyed on, default the text itself.
        urgent: wait up to 2 s for current speech to finish instead of
        dropping. Only for ground hazards, where a dropped warning means the
        user steps into a hole with only the vibration to go on.
        on_start: called the moment audio starts, used for the sync buzz.
        part_keys: one repeat key per object in the sentence. Each object then
        gets its own timer, so a chair is not muted because the person next
        to it was just announced. The caller has already picked fresh ones."""
        key = key or text
        repeat_after = self.repeat_after if repeat_after is None else repeat_after
        if self.dry_run:
            now = time.time()
            if not part_keys and now - self.last_said.get(key, 0) < repeat_after:
                return
            self.last_said[key] = now
            for k in part_keys or ():
                self.last_said[k] = now
            print(f"  WOULD SAY: {text}")
            self._note(text)
            if on_start is not None:
                on_start()
            return

        # Check the link BEFORE consuming the repeat timer, so a phrase muted
        # by a dead sink is still spoken once audio comes back.
        if not self.link.alive():
            self.link.try_reconnect()
            return

        now = time.time()
        if not part_keys and now - self.last_said.get(key, 0) < repeat_after:
            if self.verbose:
                print(f"  (muted) {text}")
            return
        if urgent:
            self.last_said[key] = now
            threading.Thread(target=self._say_when_free, args=(text,),
                             daemon=True).start()
            return
        if not self.busy.acquire(blocking=False):
            if self.verbose:
                print(f"  (still speaking, dropped) {text}")
            return
        self.last_said[key] = now
        for k in part_keys or ():
            self.last_said[k] = now
        print(f"  SPEAKING: {text}")
        self._note(text)
        threading.Thread(target=self._play, args=(text, on_start),
                         daemon=True).start()

    def say_blocking(self, text, wait=6.0):
        """Speak now and return when done. For the assistant, whose answer
        must not be dropped just because a detection phrase is playing.
        Detection phrases that arrive meanwhile are dropped as usual."""
        if self.dry_run:
            print(f"  WOULD SAY: {text}")
            self._note(text, "assistant")
            return
        if not self.link.alive():
            self.link.try_reconnect()
            return
        if self.busy.acquire(timeout=wait):
            print(f"  SPEAKING (assistant): {text}")
            self._note(text, "assistant")
            self._play(text)

    def _say_when_free(self, text):
        if self.busy.acquire(timeout=2.0):
            print(f"  SPEAKING (urgent): {text}")
            self._note(text, "hazard")
            self._play(text)
        else:
            print(f"  (urgent dropped, speech stuck) {text}", file=sys.stderr)


def watchdog(link, speaker, keepalive_after, stop):
    """Background health loop: keeps the headset awake and reconnects it."""
    while not stop.is_set():
        time.sleep(5)
        if not link.alive():
            link.try_reconnect()
            continue
        idle = time.time() - speaker.last_sound
        if keepalive_after and idle > keepalive_after:
            if speaker.busy.acquire(blocking=False):
                try:
                    link.keepalive("/tmp/cane_keepalive.wav")
                    speaker.last_sound = time.time()
                finally:
                    speaker.busy.release()


# Buzz sent to the ESP32 the moment a sentence starts, so the user feels and
# hears the same object at once. Only ToF 1 (forward) sets the strength, on
# the same range as the ESP32's own obstacle feel (CLOSE_MM / FAR_MM in
# cane_safety.ino): the nearer, the stronger and longer. A camera guess is not
# a measured distance, so it never makes the buzz stronger (Adeel, 3 Oct 2026).
# 8 Oct 2026: Adeel felt the old 60 % / 150 ms floor as "nearly negligible".
# A coin motor barely spins up in 150 ms at 60 %, so the floor is now 80 % for
# 200 ms, and the firmware kicks the motor at full power for its first 40 ms.
BUZZ_CLOSE_MM, BUZZ_FAR_MM = 400, 1500
LIGHT_BUZZ = "B80,200"   # named, but not measured by ToF 1


def tof_buzz(mm):
    """Buzz for a forward ToF distance, on a smooth scale: 80 % for 200 ms at
    1.5 m and beyond, up to 100 % for 450 ms at 0.4 m and nearer."""
    c = min(1.0, max(0.0, (BUZZ_FAR_MM - mm) / (BUZZ_FAR_MM - BUZZ_CLOSE_MM)))
    return f"B{round(80 + 20 * c)},{round(200 + 250 * c)}"


def sync_buzz(phrases, fwd_mm):
    """Buzz for a sentence about to be spoken. Something named 'ahead' that
    ToF 1 is measuring: scaled by that distance. Anything else (left, right,
    or no ToF reading): one fixed light buzz. Nothing to say: no buzz."""
    if not phrases:
        return None
    if any(tof_measures(p, fwd_mm) for p in phrases):
        return tof_buzz(fwd_mm)
    return LIGHT_BUZZ


HAZARD_PHRASES = {
    "drop": "Careful, drop ahead",   # hole, open drain, step down, kerb edge
    "step": "Step up ahead",         # kerb, step up (never an obstacle)
}


class SensorWatch:
    """Speaks what only the ESP32's ToF sensors know.

    The ESP32 has already buzzed by the time any of this runs. Speech adds the
    words: ground hazards, obstacles the camera cannot name, and a warning if
    the sensor link itself goes quiet, because a cane that silently loses its
    sensors looks healthy while protecting nobody.
    """

    # The link gets this long after start-up before silence counts as a fault,
    # so the cane no longer says "distance sensors not responding" at every
    # start just because the first reading has not arrived yet.
    STARTUP_GRACE_S = 3.0
    # Ground sensor working but no ground learned for this long: it cannot
    # reach the ground (aimed too far ahead, dark asphalt) and no drop will
    # ever be reported. Before 8 Oct 2026 that state was silent.
    NO_GROUND_S = 20.0

    def __init__(self, link, speaker, obstacle_mm, stop):
        self.link = link
        self.speaker = speaker
        self.obstacle_mm = obstacle_mm
        self.stop = stop
        self.camera_ahead_at = 0.0   # last time the ToF reading was given to a
                                     # named object ahead
        self.bad_since = {}          # sensor name -> when it started failing
        self.no_ground_since = None
        self.started = time.time()
        link.on_hazard = self.on_hazard

    def on_hazard(self, kind, mm):
        text = HAZARD_PHRASES.get(kind)
        if text:
            print(f"  GROUND {kind}: {mm} mm")
            self.speaker.say(text, urgent=True, repeat_after=2.5)

    def run(self):
        was_alive = True
        while not self.stop.is_set():
            time.sleep(0.2)
            if time.time() - self.started < self.STARTUP_GRACE_S:
                continue
            if not self.link.alive(within=2.0):
                if was_alive:
                    print("  ESP32 LINK SILENT", file=sys.stderr)
                was_alive = False
                self.speaker.say("Warning, distance sensors not responding",
                                 key="esp32-dead", repeat_after=30)
                continue
            if not was_alive:
                print("  ESP32 link back")
                was_alive = True
            # One sensor dead while the ESP32 itself is fine. Same rule: the
            # user must know they have lost pothole or obstacle warnings. The
            # ESP32 re-inits a dead sensor every second, so 3 s of failure is
            # a real fault, not a hiccup.
            now = time.time()
            for name, ok in (("ground", self.link.down_ok),
                             ("obstacle", self.link.fwd_ok)):
                if ok:
                    self.bad_since.pop(name, None)
                elif now - self.bad_since.setdefault(name, now) > 3:
                    self.speaker.say(f"Warning, {name} sensor not working",
                                     key=f"{name}-sensor-dead", repeat_after=60)
            if self.link.down_ok and self.link.ground_mm is None:
                if self.no_ground_since is None:
                    self.no_ground_since = now
                elif now - self.no_ground_since > self.NO_GROUND_S:
                    self.speaker.say("Ground sensor cannot see the ground",
                                     key="no-ground", repeat_after=300)
            else:
                self.no_ground_since = None
            mm = self.link.fwd_mm if self.link.fwd_ok else None
            # Something solid ahead that the camera has not named recently:
            # glass, a pole, a wall, anything outside the model's classes.
            if (mm is not None and mm < self.obstacle_mm
                    and time.time() - self.camera_ahead_at > 2.5):
                cmd = tof_buzz(mm)
                self.speaker.say(f"obstacle ahead, {spoken_distance(mm)}",
                                 key=f"tof-obstacle {distance_band(mm)}",
                                 on_start=lambda c=cmd: self.link.send(c))


def main():
    ap = argparse.ArgumentParser(description="Speak what the camera sees")
    ap.add_argument("--interval", type=float, default=1.5,
                    help="seconds between detection reports")
    ap.add_argument("--conf", type=float, default=0.25,
                    help="DETECTION threshold passed to detect.py. Keep this "
                         "low so faint objects are still seen at all.")
    ap.add_argument("--name-conf", type=float, default=0.55,
                    help="NAMING threshold. Above it we say the class name, "
                         "below it we say 'obstacle'. Keep this high so names "
                         "are trustworthy.")
    ap.add_argument("--max-objects", type=int, default=2,
                    help="how many objects to speak per report")
    ap.add_argument("--repeat-after", type=float, default=4.0,
                    help="seconds before the same phrase may be repeated")
    ap.add_argument("--voice", default="en-us")
    ap.add_argument("--speed", type=int, default=165, help="words per minute")
    ap.add_argument("--bt-mac", default="B0:38:E2:19:DC:CC",
                    help="Bluetooth headset to reconnect, empty to disable")
    ap.add_argument("--retry-every", type=float, default=20.0,
                    help="seconds between reconnect attempts")
    ap.add_argument("--keepalive-after", type=float, default=45.0,
                    help="seconds of silence before a blip keeps earbuds "
                         "awake, 0 to disable")
    ap.add_argument("--confirm", type=int, default=2,
                    help="consecutive reports a class must appear in before "
                         "it is spoken. 1 disables flicker suppression")
    ap.add_argument("--no-filter", action="store_true",
                    help="speak every COCO class, not just the ones a walking "
                         "person needs")
    ap.add_argument("--all-classes", action="store_true")
    ap.add_argument("--model", help=".hef forwarded to detect.py "
                    "(default: detect.py picks the best installed one)")
    ap.add_argument("--labels", help="class names file forwarded to detect.py, "
                    "one per line, same order as the model")
    ap.add_argument("--demo-port", type=int, default=0,
                    help="serve the live laptop dashboard on this port "
                         "(e.g. 8080). 0 = off")
    ap.add_argument("--fps", type=int, default=15,
                    help="camera fps, forwarded to detect.py. Lower = "
                         "longer exposure = far better in dim light.")
    ap.add_argument("--ev", type=float, default=0.7,
                    help="exposure bias, forwarded to detect.py")
    ap.add_argument("--rotate", type=int, default=0, choices=(0, 90, 180, 270),
                    help="camera mount rotation, forwarded to detect.py")
    ap.add_argument("--corridor", type=float, default=15.0,
                    help="half-width of 'ahead' in degrees, forwarded")
    ap.add_argument("--fit", choices=("letterbox", "stretch"),
                    default="letterbox", help="forwarded to detect.py")
    ap.add_argument("--no-haptics", action="store_true",
                    help="do not drive the vibration motor")
    ap.add_argument("--motor-pin", type=int, default=18,
                    help="BCM pin the motor signal is on (header pin 12)")
    ap.add_argument("--esp32-port", default="/dev/ttyUSB0",
                    help="serial port of the ESP32 safety co-processor, "
                         "empty to run camera-only")
    ap.add_argument("--obstacle-mm", type=int, default=1000,
                    help="forward ToF distance under which an unnamed "
                         "obstacle is announced")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would be spoken, play no audio")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    link = AudioLink(args.bt_mac, args.retry_every, args.verbose)
    speaker = Speaker(args.voice, args.speed, args.repeat_after, link,
                      args.verbose, dry_run=args.dry_run)
    confirmer = Confirmer(max(1, args.confirm))

    stop = threading.Event()

    # The ESP32 owns the ToF sensors and the motor. Optional: if it is not
    # plugged in, the cane still speaks what the camera sees.
    esp = None
    watch = None
    if args.esp32_port:
        try:
            from esp32_link import Esp32Link
            esp = Esp32Link(args.esp32_port)
            watch = SensorWatch(esp, speaker, args.obstacle_mm, stop)
            threading.Thread(target=watch.run, daemon=True).start()
            print(f"ESP32 on {args.esp32_port}: ToF distances + ground watch, "
                  "vibration handled by the ESP32")
        except Exception as e:
            print(f"ESP32 unavailable ({e}), camera only")
            esp = None

    # Pi-side haptics only when there is no ESP32. The motor now hangs off the
    # ESP32, and two masters for one motor would fight. Optional either way: if
    # the motor is not wired, the cane must still speak rather than refuse to
    # start.
    haptic = None
    if not args.no_haptics and esp is None:
        try:
            from haptics import Haptics
            h = Haptics(pin=args.motor_pin)
            if h.available():
                haptic = h
                print(f"haptics on GPIO{args.motor_pin} "
                      f"(gpiochip{h.chip_num})")
            else:
                print("haptics unavailable, continuing without vibration")
        except Exception as e:
            print(f"haptics unavailable ({e}), continuing without vibration")

    if not args.dry_run:
        threading.Thread(target=watchdog,
                         args=(link, speaker, args.keepalive_after, stop),
                         daemon=True).start()

    cmd = [sys.executable, "-u", os.path.join(HERE, "detect.py"),
           "--interval", str(args.interval), "--conf", str(args.conf),
           "--fps", str(args.fps), "--ev", str(args.ev),
           "--rotate", str(args.rotate), "--corridor", str(args.corridor),
           "--fit", args.fit]
    if args.all_classes:
        cmd.append("--all-classes")
    if args.model:
        cmd += ["--model", args.model]
    if args.labels:
        cmd += ["--labels", args.labels]

    # Live dashboard for a laptop (investor demo). Off unless --demo-port.
    if args.demo_port:
        from demo_server import DemoServer
        view = "/dev/shm/cane_view.jpg"
        cmd += ["--stream-file", view]
        n = 0
        if args.labels and os.path.exists(args.labels):
            with open(args.labels) as fh:
                n = sum(1 for l in fh if l.strip())
        demo = DemoServer(args.demo_port, view, esp, args.model, n)
        try:
            demo.start()
            speaker.on_speak = demo.spoken
            print(f"demo dashboard on http://{os.uname().nodename}.local:{args.demo_port}")
        except OSError as e:
            print(f"demo dashboard unavailable ({e}), cane runs normally")

    vision_cmd = cmd

    # Every class of the loaded model may be named, not only the COCO walking
    # list. The 152-class model was trained for the cane, so its indoor
    # classes (sink, window, lamp...) are wanted too.
    relevant = set(RELEVANT)
    if args.labels and os.path.exists(args.labels):
        with open(args.labels) as fh:
            relevant |= {l.strip() for l in fh if l.strip()}

    def start_vision():
        print("starting vision...")
        # stderr goes to the journal. It went to /dev/null until 8 Oct 2026,
        # which hid why vision died ("exit 1") on four boots on 7 Oct.
        return subprocess.Popen(vision_cmd, stdout=subprocess.PIPE,
                                stderr=None, text=True, bufsize=1)

    # In a dict so the assistant's snapshot signals the current detect.py,
    # also after a restart.
    vision = {"proc": start_vision()}

    # AI assistant on the ESP32 button. Needs the ESP32 (that is where the
    # button is wired) and internet. Without either the cane works as before.
    latest = {"body": ""}
    if esp is not None:
        from assistant import Assistant

        def snapshot(timeout=2.0):
            path = "/dev/shm/cane_snapshot.jpg"
            before = os.path.getmtime(path) if os.path.exists(path) else 0
            try:
                vision["proc"].send_signal(signal.SIGUSR1)
            except OSError:
                return None
            end = time.time() + timeout
            while time.time() < end:
                if os.path.exists(path) and os.path.getmtime(path) > before:
                    with open(path, "rb") as fh:
                        return fh.read()
                time.sleep(0.05)
            return None

        def context():
            return re.sub(r"\s*@[\d.]+", "", latest["body"]) or "nothing"

        helper = Assistant(snapshot, context, speaker.say_blocking, args.bt_mac)
        esp.on_button = helper.on_button
        esp.on_button2 = helper.on_button2
        print("assistant button ready (press = describe, double press = "
              "read text, hold = ask); second button = read text")

    # If detect.py dies (camera missing, loose ribbon) the cane keeps running:
    # ESP32 alerts, vibration, buttons and Bluetooth stay up, and vision is
    # retried every 10 s. Before, the whole program exited and systemd
    # restarted it, which re-paired the earbuds and dropped button presses.
    said_ready = False
    warned_camera = False
    try:
        while not stop.is_set():
            proc = vision["proc"]
            for line in proc.stdout:
                m = REPORT.match(line.strip())
                if not m:
                    continue
                warned_camera = False
                latest["body"] = m.group(1).strip()
                if not said_ready:
                    if haptic is not None:
                        haptic.buzz("ready")
                    speaker.say("Smart cane ready")
                    said_ready = True
                    continue
                body = m.group(1).strip()
                phrases = [] if (not body or body == "clear") else \
                    [p.strip() for p in body.split("|") if p.strip()]

                if not args.no_filter:
                    phrases = resolve(phrases, relevant, args.name_conf)

                # Flicker suppression runs on every report, including empty ones,
                # so streaks decay when an object genuinely leaves the frame.
                phrases = confirmer.update(phrases)
                if not phrases:
                    continue

                phrases.sort(key=rank)

                fwd_mm = None
                if esp is not None and esp.alive() and esp.fwd_ok:
                    fwd_mm = esp.fwd_mm
                if watch is not None and any(
                        tof_measures(p, fwd_mm) for p in phrases):
                    watch.camera_ahead_at = time.time()

                # Each object has its own repeat timer. Pick the most urgent
                # ones not said recently, so in a room the cane moves on to
                # the table and the door instead of naming the same person
                # every 4 s. Identical sentences ("person right, close"
                # twice for two people) are said once.
                spoken, keys = with_tof(phrases, fwd_mm)
                picked = pick_fresh(phrases, spoken, keys, speaker.fresh,
                                    args.max_objects)
                if not picked:
                    continue
                said = [p for p, _, _ in picked]

                # Buzz BEFORE speaking, not after. Vibration reaches the user in
                # about 200 ms, a spoken sentence takes well over a second. The
                # feel says "something is there, and how urgent", the words that
                # follow say what it is. Urgency is taken from the closest thing in
                # view, not the first one named.
                if haptic is not None:
                    order = {"close": 0, "near": 1, "far": 2}
                    nearest = min(
                        (parse_dist(split_phrase(p)[2])[0] for p in phrases),
                        key=lambda d: order.get(d, 3), default=None)
                    if nearest in order:
                        haptic.for_distance(nearest)

                on_start = None
                if esp is not None:
                    cmd = sync_buzz(said, fwd_mm)
                    if cmd:
                        on_start = lambda c=cmd: esp.send(c)
                speaker.say(". ".join(s for _, s, _ in picked),
                            key=" | ".join(k for _, _, k in picked),
                            part_keys=[k for _, _, k in picked],
                            on_start=on_start)
            proc.wait()
            if stop.is_set():
                break
            print(f"vision stopped (exit {proc.returncode}), retrying in 10 s")
            if not warned_camera:
                speaker.say("Camera not working. Distance sensors still on",
                            key="camera dead")
                warned_camera = True
            stop.wait(10)
            if not stop.is_set():
                vision["proc"] = start_vision()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        vision["proc"].terminate()
        if esp is not None:
            esp.close()
        if haptic is not None:
            haptic.close()
        print("\nstopped.")


if __name__ == "__main__":
    main()
