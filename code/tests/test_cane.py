#!/usr/bin/env python3
"""Smart cane - simulation tests for the blind-user scenarios.

Runs without the camera, the Hailo, the ESP32 or audio: detections, sensor
lines and button presses are simulated, speech is captured as text. So it runs
on the Pi (where it matters) and on a PC.

    cd ~/smartcane && python3 -m unittest tests/test_cane.py -v

What it covers, in user terms:
  - every hazard the 152-class model knows is spoken by name, not "obstacle"
  - drop-offs (holes, stairs) are announced before cars, cars before benches
  - one-frame ghosts are never spoken, a real object is within 3 reports
  - an uncertain detection is still announced as "obstacle", never dropped
  - the ToF distance replaces the camera guess only for things straight ahead
  - ground drop / step warnings from the ESP32 are spoken urgently
  - the cane warns out loud when the distance sensors die
  - assistant button: press = describe then listen for a question, hold =
    read text, offline = local detection + OCR, and every failure (no
    internet, no key, no mic, no camera, a crash) says something
"""
import os
import sys
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import assistant                                    # noqa: E402
import speak_detect as sd                           # noqa: E402

LABELS = os.path.join(os.path.dirname(HERE), "smartcane152.txt")
if not os.path.exists(LABELS):
    # In the repository the label file sits with the model.
    LABELS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "models",
                          "smartcane152_v3", "smartcane152.txt")

# What a blind pedestrian must hear by name. Losing any of these to
# "obstacle" removes the reason the model was retrained.
MUST_NAME = [
    "stairs", "curb", "pothole", "open hole", "manhole", "rail track",
    "crosswalk", "traffic light", "pedestrian signal", "traffic cone",
    "barrier", "bollard", "pole", "car", "bus", "truck", "bicycle",
    "e-scooter", "person", "child", "dog", "bench", "door", "escalator",
    "bus stop sign", "wet floor sign", "construction sign",
]


class FakeLink:
    def __init__(self, alive=True):
        self._alive = alive
        self.attempts = 0

    def alive(self):
        return self._alive

    def try_reconnect(self):
        self.attempts += 1


def speaker(alive=True):
    s = sd.Speaker("en-us", 165, 4.0, FakeLink(alive), False, dry_run=True)
    s.heard = []
    orig = print

    def capture(*a, **k):
        msg = " ".join(str(x) for x in a)
        if msg.strip().startswith("WOULD SAY:"):
            s.heard.append(msg.split("WOULD SAY:", 1)[1].strip())
    sd.print = capture          # Speaker prints what it would say in dry run
    s._restore = lambda: setattr(sd, "print", orig)
    return s


class Model152(unittest.TestCase):
    def test_labels_file_has_152_unique_classes(self):
        with open(LABELS) as fh:
            names = [l.strip() for l in fh if l.strip()]
        self.assertEqual(len(names), 152)
        self.assertEqual(len(set(names)), 152)

    def test_every_safety_class_exists_in_model(self):
        with open(LABELS) as fh:
            names = {l.strip() for l in fh}
        missing = [c for c in MUST_NAME if c not in names]
        self.assertEqual(missing, [], f"not in the model: {missing}")

    def test_every_safety_class_is_spoken_by_name(self):
        for cls in MUST_NAME:
            out = sd.resolve([f"{cls} ahead, near @0.80"], sd.RELEVANT, 0.35)
            self.assertEqual(out, [f"{cls} ahead, near"], cls)

    def test_all_152_classes_are_named_or_deliberately_filtered(self):
        with open(LABELS) as fh:
            names = [l.strip() for l in fh if l.strip()]
        unnamed = [n for n in names if n not in sd.RELEVANT]
        # Household clutter may stay unnamed (spoken as "obstacle"), but no
        # outdoor hazard may.
        hazards = set(MUST_NAME)
        self.assertFalse(hazards & set(unnamed), hazards & set(unnamed))


class Urgency(unittest.TestCase):
    def test_drop_offs_before_vehicles_before_furniture(self):
        phrases = ["bench left, near", "car right, far", "stairs ahead, close",
                   "person ahead, near", "open hole ahead, near"]
        phrases.sort(key=sd.rank)
        self.assertEqual([sd.class_of(p) for p in phrases],
                         ["open hole", "stairs", "car", "person", "bench"])

    def test_two_word_classes_parse(self):
        self.assertEqual(sd.split_phrase("traffic cone left, near @0.61"),
                         ("traffic cone", "left", "near", 0.61))


class Flicker(unittest.TestCase):
    def test_one_frame_ghost_is_never_spoken(self):
        c = sd.Confirmer(3)
        self.assertEqual(c.update(["dog ahead, near"]), [])
        for _ in range(5):
            self.assertEqual(c.update([]), [])

    def test_real_object_spoken_on_third_report(self):
        c = sd.Confirmer(3)
        self.assertEqual(c.update(["stairs ahead, near"]), [])
        self.assertEqual(c.update(["stairs ahead, near"]), [])
        self.assertEqual(c.update(["stairs ahead, near"]), ["stairs ahead, near"])

    def test_single_dropout_is_forgiven(self):
        c = sd.Confirmer(3)
        for _ in range(3):
            c.update(["car left, far"])
        c.update([])                                  # one missed frame
        self.assertEqual(c.update(["car left, far"]), ["car left, far"])


class NeverSilent(unittest.TestCase):
    def test_uncertain_detection_becomes_obstacle(self):
        out = sd.resolve(["stairs ahead, near @0.28"], sd.RELEVANT, 0.35)
        self.assertEqual(out, ["obstacle ahead, near"])

    def test_unknown_class_becomes_obstacle(self):
        out = sd.resolve(["toothbrush left, close @0.9"], sd.RELEVANT, 0.35)
        self.assertEqual(out, ["obstacle left, close"])

    def test_clutter_collapses_to_one_obstacle(self):
        out = sd.resolve(["toothbrush left, near @0.3", "spoon left, near @0.3"],
                         sd.RELEVANT, 0.35)
        self.assertEqual(out, ["obstacle left, near"])


class Distance(unittest.TestCase):
    def test_tof_replaces_camera_guess_only_ahead(self):
        spoken, _ = sd.with_tof(["pole ahead, far", "car left, near"], 640)
        self.assertEqual(spoken, ["pole ahead, 0.6 meters", "car left, near"])

    def test_spoken_distances_are_in_meters(self):
        self.assertEqual(sd.spoken_distance(999), "1 meter")
        self.assertEqual(sd.spoken_distance(1240), "1.2 meters")
        self.assertEqual(sd.spoken_distance(640), "0.6 meters")
        self.assertEqual(sd.spoken_distance(30), "0.1 meters")

    def test_camera_estimate_spoken_as_about_meters(self):
        spoken, _ = sd.with_tof(["chair left, near 2.4m", "table right, far 4.1m"], None)
        self.assertEqual(spoken, ["chair left, about 2.5 meters",
                                  "table right, about 4 meters"])

    def test_tof_not_given_to_object_it_is_not_measuring(self):
        # Camera says the person is ~4 m away, the ToF beam hits something at
        # 0.8 m: that is not the person.
        spoken, _ = sd.with_tof(["person ahead, far 4.0m"], 800)
        self.assertEqual(spoken, ["person ahead, about 4 meters"])
        spoken, _ = sd.with_tof(["person ahead, near 1.4m"], 1250)
        self.assertEqual(spoken, ["person ahead, 1.2 meters"])

    def test_closer_object_is_repeated_despite_timer(self):
        _, far = sd.with_tof(["person ahead, far"], 1100)
        _, close = sd.with_tof(["person ahead, far"], 400)
        self.assertNotEqual(far, close)

    def test_small_estimate_changes_do_not_repeat(self):
        _, a = sd.with_tof(["chair left, near 3.1m"], None)
        _, b = sd.with_tof(["chair left, near 3.4m"], None)
        self.assertEqual(a, b)

    def test_buzz_full_power_and_longer_when_closer(self):
        self.assertEqual(sd.tof_buzz(2000), "B100,300")
        self.assertEqual(sd.tof_buzz(300), "B100,500")
        self.assertEqual(sd.sync_buzz(["car left, far"], 500), sd.LIGHT_BUZZ)
        self.assertIsNone(sd.sync_buzz([], 500))


class MoreObjects(unittest.TestCase):
    """In a room the cane must move on from the person to the furniture."""

    def test_identical_sentences_said_once(self):
        ph = ["person right, close", "person right, close", "chair left, near"]
        spoken, keys = sd.with_tof(ph, None)
        got = sd.pick_fresh(ph, spoken, keys, lambda k: True, 2)
        self.assertEqual([s for _, s, _ in got],
                         ["person right, close", "chair left, near"])

    def test_recently_said_object_makes_room_for_the_next(self):
        s = speaker()
        try:
            ph = ["person ahead, near 2.0m", "chair left, near 2.4m",
                  "table right, near 2.2m"]
            for _ in range(2):
                spoken, keys = sd.with_tof(ph, None)
                got = sd.pick_fresh(ph, spoken, keys, s.fresh, 2)
                s.say(". ".join(x for _, x, _ in got), part_keys=[k for _, _, k in got])
            self.assertEqual(s.heard, [
                "person ahead, about 2 meters. chair left, about 2.5 meters",
                "table right, about 2 meters"])
        finally:
            s._restore()


class Geometry(unittest.TestCase):
    """detect.py's picture handling, without a camera."""

    def setUp(self):
        try:
            import numpy  # noqa: F401
            import detect
        except ImportError as e:
            self.skipTest(f"needs numpy and PIL ({e})")
        self.d = detect

    def test_real_fov_of_the_cropped_sensor_mode(self):
        self.assertAlmostEqual(self.d.effective_hfov(120, 3072, 4608), 98.2, places=1)

    def test_letterbox_maps_boxes_back(self):
        import numpy as np
        f = np.zeros((360, 640, 3), np.uint8)
        inp, region = self.d.prepare(f, 640, 640)
        self.assertEqual(inp.shape, (640, 640, 3))
        self.assertEqual(int(inp[0, 0, 0]), self.d.PAD_VALUE)
        # a box over the middle of the picture, in input coordinates
        raw = [[np.array([(140 + 90) / 640, 0.25, (140 + 270) / 640, 0.75, 0.9])]]
        (det,) = self.d.extract_detections(raw, ["chair"], 1280, 720, 0.25, region)
        self.assertEqual((round(det.x0), round(det.y0), round(det.x1), round(det.y1)),
                         (320, 180, 960, 540))

    def test_rotate_90_turns_clockwise(self):
        import numpy as np
        f = np.zeros((360, 640, 3), np.uint8)
        f[100:200, 300:400] = 255
        inp, _ = self.d.prepare(f, 640, 640, rotate=90)
        ys, xs = np.where(inp[:, :, 0] == 255)
        self.assertEqual((ys.min(), ys.max(), xs.min(), xs.max()), (300, 399, 300, 399))

    def test_ahead_when_box_crosses_the_centre_line(self):
        self.assertEqual(self.d.zone(500, 1000, 1280, 98, 15), "ahead")
        self.assertEqual(self.d.zone(900, 1100, 1280, 98, 15), "right")
        self.assertEqual(self.d.zone(100, 300, 1280, 98, 15), "left")

    def test_distance_estimate_and_cut_off_boxes(self):
        D = self.d.Detection
        person = D("person", 0.9, 600, 200, 700, 600)        # 400 px tall
        self.assertAlmostEqual(self.d.estimate_m(person, 1280, 720, 98.2), 2.29, places=2)
        cut = D("person", 0.9, 600, 0, 700, 600)              # head out of frame
        self.assertIsNone(self.d.estimate_m(cut, 1280, 720, 98.2))
        self.assertIsNone(self.d.estimate_m(D("pole", 0.9, 0, 100, 10, 300), 1280, 720, 98.2))
        self.assertEqual(self.d.describe([person], 1280, 720, 4, 98.2, 15),
                         "person ahead, close 2.3m @0.90")

    def test_one_object_one_name(self):
        D = self.d.Detection
        kept = self.d.dedupe([D("desk", 0.6, 5, 5, 100, 100), D("table", 0.8, 0, 0, 100, 100),
                              D("chair", 0.7, 200, 0, 300, 100)])
        self.assertEqual([k.label for k in kept], ["table", "chair"])


class Esp32Serial(unittest.TestCase):
    """Real Esp32Link on a pseudo-terminal, fed the firmware's exact lines."""

    def setUp(self):
        try:
            import serial  # noqa: F401
        except ImportError:
            self.skipTest("pyserial not installed")
        if os.name != "posix":
            self.skipTest("needs a pty (run on the Pi)")
        import pty
        import tty
        from esp32_link import Esp32Link
        self.master, slave = pty.openpty()
        tty.setraw(slave)
        self.link = Esp32Link(os.ttyname(slave))

    def tearDown(self):
        if hasattr(self, "link"):
            self.link.close()

    def feed(self, *lines):
        for l in lines:
            os.write(self.master, (l + "\n").encode())
        time.sleep(0.4)

    def test_distance_report(self):
        self.feed("D 1000 640 1350 1 1 1300")
        self.assertEqual((self.link.fwd_mm, self.link.fwd_ok), (640, True))

    def test_ground_drop_and_button(self):
        got = []
        self.link.on_hazard = lambda k, mm: got.append((k, mm))
        self.link.on_button = lambda p: got.append(("button", p))
        self.feed("H drop 1650 1300", "K down", "K up", "I ground learned 1300")
        self.assertEqual(got, [("drop", 1650), ("button", True), ("button", False)])

    def test_hazard_warning_is_spoken(self):
        s = speaker()
        try:
            w = sd.SensorWatch(self.link, s, 1000, threading.Event())
            self.feed("H drop 1650 1300", "H step 1100 1300")
            time.sleep(2.5)                        # urgent path waits for lock
            self.assertIn("Careful, drop ahead", s.heard)
            self.assertIn("Step up ahead", s.heard)
            del w
        finally:
            s._restore()

    def test_dead_sensor_link_is_announced(self):
        s = speaker()
        stop = threading.Event()
        try:
            w = sd.SensorWatch(self.link, s, 1000, stop)
            w.STARTUP_GRACE_S = 3.0                # the real 20 s would slow the test
            threading.Thread(target=w.run, daemon=True).start()
            time.sleep(9.6)                        # no D lines: grace 3 s + 6 s silence
            stop.set()
            self.assertIn("Warning, distance sensors not responding", s.heard)
        finally:
            s._restore()

    def test_start_up_stall_is_not_announced(self):
        # Every start on 8 and 9 Oct 2026: no data for ~10 s after power-on.
        s = speaker()
        stop = threading.Event()
        try:
            w = sd.SensorWatch(self.link, s, 1000, stop)
            threading.Thread(target=w.run, daemon=True).start()
            time.sleep(9.0)                        # silent, like the first open
            for _ in range(5):
                self.feed("D 1000 640 1350 1 1 1300")
            stop.set()
            self.assertNotIn("Warning, distance sensors not responding", s.heard)
        finally:
            s._restore()

    def test_no_warning_during_start_up(self):
        s = speaker()
        stop = threading.Event()
        try:
            w = sd.SensorWatch(self.link, s, 1000, stop)
            threading.Thread(target=w.run, daemon=True).start()
            time.sleep(0.5)
            self.feed("D 1000 640 1350 1 1 1300")
            for _ in range(8):                     # keep the link alive 2 s
                self.feed("D 1000 640 1350 1 1 1300")
            stop.set()
            self.assertNotIn("Warning, distance sensors not responding", s.heard)
        finally:
            s._restore()

    def test_silent_port_is_reopened(self):
        self.link.SILENT_REOPEN_S = 0.5
        self.link.REOPEN_EVERY_S = 0.5
        time.sleep(1.5)                            # nothing arrives
        self.assertGreaterEqual(self.link.reopens, 1)

    def test_clock_jump_is_not_silence(self):
        # 9 Oct 2026: NTP moved the clock 17 h forward after a cold start and
        # the cane said "distance sensors not responding" with both working.
        from unittest import mock
        self.feed("D 1000 640 1350 1 1 1300")
        later = time.time() + 17 * 3600
        with mock.patch("time.time", return_value=later):
            self.assertTrue(self.link.alive(within=6))
            time.sleep(0.5)
        self.assertEqual(self.link.reopens, 0)
        self.feed("D 1000 640 1350 1 1 1300")      # and it still reads after
        self.assertEqual(self.link.fwd_mm, 640)


def wav_bytes(seconds, tone_from=None, tone_to=None, rate=16000, amp=6000):
    """16-bit mono WAV: quiet noise, with a 300 Hz tone between tone_from and
    tone_to seconds (a stand-in for a voice)."""
    import io
    import math
    import random
    import struct
    import wave
    rnd = random.Random(1)
    frames = bytearray()
    for i in range(int(seconds * rate)):
        t = i / rate
        v = rnd.randint(-40, 40)
        if tone_from is not None and tone_from <= t < tone_to:
            v += int(amp * math.sin(2 * math.pi * 300 * t))
        frames += struct.pack("<h", max(-32768, min(32767, v)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return buf.getvalue()


class AssistantButton(unittest.TestCase):
    """One button: short press = assistant (describe, then listen for a
    question), long press = read text, offline = local detection + OCR.
    Gemini, the network, the mic and Tesseract are faked."""

    class Mic:
        def __init__(self, ok=True, wav=None):
            self.ok, self.wav, self.started = ok, wav, 0

        def start(self):
            self.started += 1
            if self.ok:
                with open(assistant.QUESTION_WAV, "wb") as fh:
                    fh.write(self.wav or wav_bytes(1.0))     # silence
            return self.ok

        def stop(self):
            pass

    def make(self, mic=None, jpeg=b"\xff\xd8fake", replies=None, error=None,
             key="k", net=True, ocr="EXIT"):
        self.said, self.prompts, self.cues, self.holds = [], [], [], []
        replies = list(replies or ["A clear pavement ahead."])
        a = assistant.Assistant(
            lambda: jpeg, lambda: "car left", self.said.append,
            "00:00:00:00:00:00", mic=mic or self.Mic(),
            cue=self.cues.append,
            local_summary=lambda: "car left, about 4 meters",
            hold_speech=self.holds.append, is_online=lambda: net)
        a.listen_s = 0.4

        def fake(k, prompt, j, wav, ctx):
            self.prompts.append((prompt, wav is not None))
            if error:
                raise RuntimeError(error)
            return replies.pop(0) if len(replies) > 1 else replies[0]
        self._orig = (assistant.gemini, assistant.load_key, assistant.ocr_offline,
                      assistant.STUCK_S)
        assistant.gemini = fake
        assistant.load_key = lambda: key
        assistant.ocr_offline = lambda j: ocr
        return a

    def tearDown(self):
        (assistant.gemini, assistant.load_key, assistant.ocr_offline,
         assistant.STUCK_S) = self._orig

    def press(self, a, hold):
        a.on_button(True)
        time.sleep(hold)
        a.on_button(False)

    def settle(self, a, t=0.3):
        time.sleep(t)
        self.assertTrue(a.busy.acquire(timeout=8), "assistant never finished")
        a.busy.release()

    # -- short press, online --

    def test_short_press_describes_then_listens(self):
        a = self.make()
        self.press(a, 0.1)
        self.settle(a)
        self.assertEqual(self.prompts, [(assistant.DESCRIBE, False)])
        self.assertEqual(self.said, ["Looking", "A clear pavement ahead."])
        self.assertEqual(self.cues, ["listen"])        # buzz: speak now
        self.assertEqual(self.holds, [True, False])     # announcements paused

    def test_spoken_question_is_answered(self):
        a = self.make(mic=self.Mic(wav=wav_bytes(1.5, 0.3, 1.2)),
                      replies=["A doorway ahead.", "The sign says Exit."])
        self.press(a, 0.1)
        self.settle(a)
        self.assertEqual(self.prompts, [(assistant.DESCRIBE, False), (assistant.ASK, True)])
        self.assertEqual(self.said[-1], "The sign says Exit.")

    def test_no_question_reply_stays_silent(self):
        a = self.make(mic=self.Mic(wav=wav_bytes(1.5, 0.3, 1.2)),
                      replies=["A doorway ahead.", "NO_QUESTION"])
        self.press(a, 0.1)
        self.settle(a)
        self.assertEqual(self.said, ["Looking", "A doorway ahead."])

    def test_silence_is_not_sent(self):
        a = self.make()                                  # mic records silence
        self.press(a, 0.1)
        self.settle(a)
        self.assertEqual(len(self.prompts), 1)

    def test_press_while_listening_stops_early(self):
        a = self.make()
        a.listen_s = 5.0
        self.press(a, 0.1)
        for _ in range(100):                             # wait for the mic
            if a.listening.is_set():
                break
            time.sleep(0.02)
        self.assertTrue(a.listening.is_set())
        t0 = time.time()
        self.press(a, 0.05)
        self.settle(a, 0.1)
        self.assertLess(time.time() - t0, 2.0)

    def test_no_mic_skips_listening(self):
        a = self.make(mic=self.Mic(ok=False))
        self.press(a, 0.1)
        self.settle(a)
        self.assertEqual(self.said, ["Looking", "A clear pavement ahead."])
        self.assertEqual(self.cues, [])

    def test_busy_service_retries_once(self):
        a = self.make(error="assistant busy, try again")
        self.press(a, 0.1)
        self.settle(a, 3.0)
        self.assertEqual(len(self.prompts), 2)
        self.assertIn("Still looking", self.said)

    def test_gemini_error_still_gives_local_answer(self):
        a = self.make(error="free assistant limit reached, try again in a minute")
        self.press(a, 0.1)
        self.settle(a)
        self.assertIn("free assistant limit reached, try again in a minute", self.said)
        self.assertEqual(self.said[-2:], ["car left, about 4 meters.", "Text reads: EXIT"])

    # -- short press, offline --

    def test_offline_press_uses_detector_and_local_ocr(self):
        a = self.make(net=False)
        self.press(a, 0.1)
        self.settle(a)
        self.assertEqual(self.prompts, [])
        self.assertEqual(self.said, ["No internet, offline mode. car left, about 4 meters.",
                                     "Text reads: EXIT"])

    def test_offline_without_text(self):
        a = self.make(net=False, ocr="")
        self.press(a, 0.1)
        self.settle(a)
        self.assertEqual(self.said, ["No internet, offline mode. car left, about 4 meters."])

    def test_no_key_works_offline(self):
        a = self.make(key="")
        self.press(a, 0.1)
        self.settle(a)
        self.assertTrue(self.said[0].startswith("No assistant key, offline mode."))

    # -- long press --

    def test_long_press_reads_text_online(self):
        a = self.make(replies=["Exit"])
        self.press(a, 1.2)
        self.settle(a)
        self.assertEqual(self.prompts, [(assistant.READ, False)])
        self.assertEqual(self.said, ["Reading", "Exit"])
        self.assertEqual(self.cues, ["hold"])            # buzz at 1 s

    def test_long_press_offline_reads_locally(self):
        a = self.make(net=False)
        self.press(a, 1.2)
        self.settle(a)
        self.assertEqual(self.said, ["Reading", "Offline reading. EXIT"])

    def test_long_press_falls_back_to_ocr_when_gemini_fails(self):
        a = self.make(error="free assistant limit reached, try again in a minute")
        self.press(a, 1.2)
        self.settle(a)
        self.assertEqual(self.said[-1], "Offline reading. EXIT")

    def test_long_press_no_text(self):
        a = self.make(net=False, ocr="")
        self.press(a, 1.2)
        self.settle(a)
        self.assertEqual(self.said[-1], "No text found")

    # -- faults --

    def test_camera_failure_is_spoken(self):
        a = self.make(jpeg=None)
        self.press(a, 0.1)
        self.settle(a)
        self.assertEqual(self.said, ["Camera not ready"])

    def test_presses_during_an_answer_are_ignored(self):
        a = self.make()
        a.busy.acquire()
        try:
            self.press(a, 0.1)
            time.sleep(0.5)
        finally:
            a.busy.release()
        self.assertEqual(self.prompts, [])

    def test_stuck_switch_is_ignored(self):
        a = self.make()
        assistant.STUCK_S = 0.3
        self.press(a, 0.5)
        time.sleep(0.5)
        self.assertEqual(self.prompts, [])
        self.assertEqual(self.said, [])

    def test_crash_inside_is_spoken_and_releases(self):
        a = self.make()
        a.local_summary = lambda: 1 / 0
        a.is_online = lambda: False
        self.press(a, 0.1)
        self.settle(a)
        self.assertEqual(self.said[-1], "Assistant error")
        self.assertEqual(self.holds, [True, False])


class AssistantParts(unittest.TestCase):
    def test_voice_check(self):
        self.assertFalse(assistant.has_speech(wav_bytes(1.0)))
        self.assertTrue(assistant.has_speech(wav_bytes(1.5, 0.3, 1.0)))
        self.assertFalse(assistant.has_speech(b"\0" * 32000))      # no header
        self.assertFalse(assistant.has_speech(wav_bytes(0.1, 0, 0.1)))  # too short
        # speech from start to end, no quiet floor (pressed to stop early)
        self.assertTrue(assistant.has_speech(wav_bytes(1.2, 0, 1.2)))

    def test_network_failure_stops_after_one_request(self):
        import urllib.error
        import urllib.request
        calls = []

        def boom(*a, **k):
            calls.append(1)
            raise urllib.error.URLError("no route")
        orig = urllib.request.urlopen
        urllib.request.urlopen = boom
        try:
            with self.assertRaises(RuntimeError) as cm:
                assistant.gemini("k", "hi")
        finally:
            urllib.request.urlopen = orig
        self.assertEqual(len(calls), 1)
        self.assertIn("no internet", str(cm.exception))

    def test_slow_model_hands_over_to_the_next(self):
        import io
        import json
        import urllib.request
        calls = []

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake(req, timeout=None):
            calls.append(req.full_url)
            if len(calls) == 1:
                raise TimeoutError("read timed out")
            return Resp(json.dumps({"candidates": [{"content": {"parts": [
                {"text": "A bench ahead."}]}}]}).encode())
        orig = urllib.request.urlopen
        urllib.request.urlopen = fake
        try:
            self.assertEqual(assistant.gemini("k", "hi"), "A bench ahead.")
        finally:
            urllib.request.urlopen = orig
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0], calls[1])          # a different model

    def test_online_check_is_quick_when_unreachable(self):
        t0 = time.time()
        self.assertFalse(assistant.online("unreachable.invalid", timeout=1.0))
        self.assertLess(time.time() - t0, 3.0)

    def test_offline_summary_sentence(self):
        body = "chair ahead, near 1.4m @0.82 | backpack left, near 1.3m @0.75 | spoon right, far @0.30"
        self.assertEqual(
            sd.summarize(body, sd.RELEVANT | {"chair"}, 0.35, 1250),
            "chair ahead, 1.2 meters. backpack left, about 1.5 meters. obstacle right, far")
        self.assertEqual(sd.summarize("clear", sd.RELEVANT, 0.35, None), "")

    def test_speech_pause_keeps_urgent_warnings(self):
        s = speaker()
        try:
            s.hold(True)
            self.assertFalse(s.say("chair ahead, 1 meter", routine=True))
            self.assertTrue(s.say("Careful, drop ahead", urgent=True, repeat_after=2.5))
            self.assertTrue(s.say("Warning, ground sensor not working"))
            s.hold(False)
            self.assertTrue(s.say("chair ahead, 1 meter", routine=True))
            self.assertEqual(s.heard, ["Careful, drop ahead",
                                       "Warning, ground sensor not working",
                                       "chair ahead, 1 meter"])
        finally:
            s._restore()


class DemoDashboard(unittest.TestCase):
    """The laptop dashboard shows what the cane says and serves all 3 URLs."""

    def test_spoken_words_reach_dashboard(self):
        import demo_server
        s = speaker()
        try:
            d = demo_server.DemoServer(0, os.path.join(assistant.SHM, "x.jpg"))
            s.on_speak = d.spoken
            s.say("stairs ahead, near")
            s.say_blocking("Bus stop 42")
            said = d.state()["said"]
            self.assertEqual([(x["text"], x["kind"]) for x in said],
                             [("stairs ahead, near", "speech"),
                              ("Bus stop 42", "assistant")])
        finally:
            s._restore()

    def test_page_stream_and_events_are_served(self):
        import json
        import socket
        import urllib.request
        import demo_server
        from PIL import Image
        view = os.path.join(assistant.SHM, "cane_view_test.jpg")
        Image.new("RGB", (64, 36), (40, 40, 40)).save(view)
        with open(os.path.splitext(view)[0] + ".json", "w") as fh:
            json.dump({"fps": 10, "infer_ms": 30, "dets": []}, fh)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        httpd = demo_server.DemoServer(port, view, model="m.hef", n_classes=152).start()
        try:
            base = f"http://127.0.0.1:{port}"
            page = urllib.request.urlopen(base + "/", timeout=5).read()
            self.assertIn(b"OmniWalk", page)
            with urllib.request.urlopen(base + "/stream.mjpg", timeout=5) as r:
                # Part header (~70 bytes) then the JPEG's start marker. The
                # stream never ends, so read a fixed small amount.
                self.assertIn(b"\xff\xd8", r.read(120))
            with urllib.request.urlopen(base + "/events", timeout=5) as r:
                line = r.readline().decode()
            state = json.loads(line[len("data: "):])
            self.assertEqual((state["classes"], state["vision"]["fps"]), (152, 10))
        finally:
            httpd.shutdown()

    def test_frames_drawn_only_while_watched(self):
        # With nobody watching, detect.py must not spend CPU drawing frames.
        import demo_view
        view = os.path.join(assistant.SHM, "cane_view_watch.jpg")
        v = demo_view.Viewer(view, 640, 360, 98.2, 10, info=lambda d: {})
        if os.path.exists(v.watch_path):
            os.remove(v.watch_path)
        self.assertFalse(v.due())
        open(v.watch_path, "a").close()
        self.assertTrue(v.due())
        old = time.time() - demo_view.WATCH_S - 1
        os.utime(v.watch_path, (old, old))
        self.assertFalse(v.due())

    def test_requests_mark_watched_only_with_token(self):
        import socket
        import urllib.error
        import urllib.request
        import demo_server
        view = os.path.join(assistant.SHM, "cane_view_tok.jpg")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        d = demo_server.DemoServer(port, view, token="s3cret", host="127.0.0.1")
        if os.path.exists(d.watch_path):
            os.remove(d.watch_path)
        httpd = d.start()
        try:
            base = f"http://127.0.0.1:{port}"
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(base + "/state.json", timeout=5)
            self.assertEqual(e.exception.code, 403)
            self.assertFalse(os.path.exists(d.watch_path))
            urllib.request.urlopen(base + "/state.json?token=s3cret&n=1", timeout=5).read()
            self.assertTrue(os.path.exists(d.watch_path))
        finally:
            httpd.shutdown()

    def test_frame_after_waits_for_a_new_frame(self):
        # The dashboard asks for "a frame newer than the one I have": the same
        # picture is never sent twice, and a new one goes out at once.
        import socket
        import urllib.request
        import demo_server
        view = os.path.join(assistant.SHM, "cane_view_after.jpg")
        with open(view, "wb") as fh:
            fh.write(b"\xff\xd8one")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        d = demo_server.DemoServer(port, view, host="127.0.0.1")
        d.frame_wait = 0.3
        httpd = d.start()
        try:
            base = f"http://127.0.0.1:{port}/frame.jpg"
            with urllib.request.urlopen(base, timeout=5) as r:
                first = r.headers["X-Frame"]
                self.assertEqual(r.read(), b"\xff\xd8one")
                self.assertIn("X-Frame", r.headers["Access-Control-Expose-Headers"])
            with urllib.request.urlopen(f"{base}?after={first}", timeout=5) as r:
                self.assertEqual((r.status, r.read()), (204, b""))
            time.sleep(0.01)
            tmp = view + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(b"\xff\xd8two")
            os.replace(tmp, view)
            with urllib.request.urlopen(f"{base}?after={first}", timeout=5) as r:
                self.assertEqual(r.read(), b"\xff\xd8two")
                self.assertGreater(int(r.headers["X-Frame"]), int(first))
        finally:
            httpd.shutdown()
            os.remove(view)

    def test_view_keeps_colours(self):
        # picamera2 gives B, G, R, X bytes: a blue scene must stay blue on
        # the dashboard, whichever resize path (OpenCV or PIL) is used.
        import numpy as np
        import demo_view
        from PIL import Image
        view = os.path.join(assistant.SHM, "cane_view_colour.jpg")
        frame = np.zeros((360, 640, 4), dtype=np.uint8)
        frame[:, :, 0] = 255                       # B
        v = demo_view.Viewer(view, 640, 360, 98.2, 10, info=lambda d: {})
        v.write(frame, [], 10.0, 30.0)
        r, g, b = Image.open(view).convert("RGB").getpixel((480, 270))
        self.assertEqual(Image.open(view).size, (960, 540))
        self.assertTrue(b > 200 and r < 50 and g < 50, (r, g, b))
        os.remove(view)
        os.remove(os.path.splitext(view)[0] + ".json")


class WifiQr(unittest.TestCase):
    """Joining Wi-Fi from a phone's QR code: parsing, decoding a real QR
    image, the nmcli calls (faked), and the long press that triggers it."""

    def setUp(self):
        import wifi_qr
        self.w = wifi_qr

    def qr_jpeg(self, text, module_px=6, size=(1280, 720)):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("OpenCV not installed")
        if not hasattr(cv2, "QRCodeEncoder"):
            self.skipTest("this OpenCV cannot draw QR codes")
        code = cv2.QRCodeEncoder.create().encode(text)
        code = cv2.resize(code, None, fx=module_px, fy=module_px,
                          interpolation=cv2.INTER_NEAREST)
        canvas = np.full((size[1], size[0]), 200, np.uint8)
        y, x = (size[1] - code.shape[0]) // 2, (size[0] - code.shape[1]) // 2
        canvas[y:y + code.shape[0], x:x + code.shape[1]] = code
        return cv2.imencode(".jpg", canvas)[1].tobytes()

    # -- the QR text --

    def test_parse_android_code(self):
        self.assertEqual(self.w.parse_wifi("WIFI:S:Home Net;T:WPA;P:secret 1;H:false;;"),
                         {"ssid": "Home Net", "password": "secret 1",
                          "security": "wpa", "hidden": False})

    def test_parse_escapes_and_order(self):
        n = self.w.parse_wifi(r'WIFI:P:a\;b\:c\\d;T:SAE;S:Caf\;e;H:true;;')
        self.assertEqual((n["ssid"], n["password"], n["security"], n["hidden"]),
                         ("Caf;e", "a;b:c\\d", "sae", True))

    def test_parse_kinds(self):
        p = self.w.parse_wifi
        self.assertEqual(p("WIFI:S:Free;T:nopass;;")["security"], "open")
        self.assertEqual(p("WIFI:S:Free;;")["security"], "open")
        self.assertEqual(p("WIFI:S:Old;T:WEP;P:abcde;;")["security"], "wep")
        self.assertEqual(p("WIFI:S:Work;T:WPA2-EAP;E:PEAP;I:me;P:x;;")["security"], "enterprise")
        self.assertEqual(p('WIFI:S:"Quoted";T:WPA;P:"pw";;')["ssid"], "Quoted")
        self.assertIsNone(p("https://example.com"))
        self.assertIsNone(p("WIFI:T:WPA;P:x;;"))           # no network name

    # -- the photo --

    def test_wifi_code_is_read_from_a_photo(self):
        net, state = self.w.look(self.qr_jpeg("WIFI:S:Test Net;T:WPA;P:pa:ss;;"))
        self.assertEqual(state, "wifi")
        self.assertEqual((net["ssid"], net["password"]), ("Test Net", "pa:ss"))

    def test_small_code_is_enlarged_until_it_reads(self):
        net, state = self.w.look(self.qr_jpeg("WIFI:S:Far;T:WPA;P:secret;;", module_px=2))
        self.assertEqual((state, net and net["ssid"]), ("wifi", "Far"))

    def test_other_codes_and_no_code(self):
        import cv2
        import numpy as np
        self.assertEqual(self.w.look(self.qr_jpeg("https://example.com"))[1], "other")
        blank = cv2.imencode(".jpg", np.full((720, 1280), 200, np.uint8))[1].tobytes()
        self.assertEqual(self.w.look(blank)[1], "none")
        self.assertEqual(self.w.look(b"\xff\xd8not a jpeg")[1], "none")

    # -- nmcli (faked) --

    def fake_nmcli(self, profiles=(), ssids=None, visible=("Cafe",), active=None,
                   up_rc=0, up_err=""):
        calls = []
        ssids = ssids or {}

        class R:
            def __init__(self, rc=0, out="", err=""):
                self.returncode, self.stdout, self.stderr = rc, out, err

        def run(cmd, **kw):
            calls.append(cmd)
            a = cmd[1:]
            if a[:5] == ["-t", "-f", "NAME,TYPE", "connection", "show"]:
                return R(out="".join(f"{p}:802-11-wireless\n" for p in profiles) + "lo:loopback\n")
            if a[:2] == ["-g", "802-11-wireless.ssid"]:
                return R(out=ssids.get(a[-1], "") + "\n")
            if a[:2] == ["-t", "-f"] and "wifi" in a:
                return R(out="".join(f"{'yes' if s == active else 'no'}:{s}:70:WPA2\n" for s in visible))
            if "up" in a:
                return R(rc=up_rc, err=up_err)
            return R()
        return run, calls

    def net(self, **kw):
        n = {"ssid": "Cafe", "password": "hunter22", "security": "wpa", "hidden": False}
        n.update(kw)
        return n

    def test_new_network_is_saved_and_joined(self):
        run, calls = self.fake_nmcli()
        self.assertEqual(self.w.join(self.net(), run=run), "Connected to Cafe.")
        add = next(c for c in calls if "add" in c)
        self.assertEqual(add[0], "nmcli")                  # never through sudo
        self.assertIn("hunter22", add)
        self.assertIn("wpa-psk", add)
        self.assertTrue(any("up" in c for c in calls))

    def test_saved_network_gets_the_new_password(self):
        run, calls = self.fake_nmcli(profiles=["preconfigured"], ssids={"preconfigured": "Cafe"})
        self.w.join(self.net(), run=run)
        self.assertFalse(any("add" in c for c in calls))
        mod = next(c for c in calls if "modify" in c)
        self.assertIn("preconfigured", mod)
        self.assertIn("hunter22", mod)

    def test_out_of_range_is_saved_without_dropping_wifi(self):
        run, calls = self.fake_nmcli(visible=("Home",))
        said = self.w.join(self.net(), run=run)
        self.assertIn("not in range", said)
        self.assertFalse(any("up" in c for c in calls))

    def test_already_connected_is_not_rejoined(self):
        run, calls = self.fake_nmcli(active="Cafe")
        self.assertIn("Already connected", self.w.join(self.net(), run=run))
        self.assertFalse(any("up" in c for c in calls))

    def test_wrong_password_is_said(self):
        run, _ = self.fake_nmcli(up_rc=4, up_err="Error: Secrets were required, but not provided.")
        self.assertIn("did not accept the password", self.w.join(self.net(), run=run))

    def test_enterprise_is_refused_without_nmcli(self):
        run, calls = self.fake_nmcli()
        self.assertIn("user name", self.w.join(self.net(security="enterprise"), run=run))
        self.assertEqual(calls, [])

    def test_password_is_never_printed(self):
        import contextlib
        import io
        out = io.StringIO()
        run, _ = self.fake_nmcli(up_rc=4, up_err="Error: Connection activation failed.")
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            said = self.w.join(self.net(), run=run)
        self.assertNotIn("hunter22", out.getvalue() + said)

    # -- the button --

    def test_long_press_on_a_wifi_code_joins_instead_of_reading(self):
        jpeg = self.qr_jpeg("WIFI:S:Cafe;T:WPA;P:hunter22;;")
        said, joined = [], []
        a = assistant.Assistant(lambda: jpeg, lambda: "", said.append, "00:00:00:00:00:00",
                                mic=object(), is_online=lambda: False)
        orig = (self.w.join, assistant.load_key, assistant.ocr_offline)
        self.w.join = lambda n: joined.append(n["ssid"]) or "Connected to Cafe."
        assistant.load_key = lambda: ""
        assistant.ocr_offline = lambda j: "SHOULD NOT READ"
        try:
            a._handle("read")
        finally:
            self.w.join, assistant.load_key, assistant.ocr_offline = orig
        self.assertEqual(joined, ["Cafe"])
        self.assertEqual(said, ["Wi-Fi code. Network Cafe. Joining", "Connected to Cafe."])
        self.assertNotIn("hunter22", " ".join(said))


class AdminPage(unittest.TestCase):
    """The owner's page: password on the cane, sessions, browser checks, and
    the Wi-Fi and Bluetooth actions (faked), plus the real HTTP server."""

    SITE = {"Host": "abc-def.trycloudflare.com", "Origin": "https://adeliusa486.github.io",
            "Cf-Connecting-Ip": "203.0.113.9"}
    HOME = {"Host": "192.168.3.51:8080", "Origin": "http://192.168.3.51:8080"}

    def setUp(self):
        import tempfile
        import types
        import admin_api
        import bt_admin
        import wifi_net
        self.dir = tempfile.mkdtemp()
        self.calls, self.said, self.ears, self.later = [], [], [], []
        calls = self.calls
        self.plan = "join"
        wifi = types.SimpleNamespace(
            HOTSPOT="OmniWalk-Setup",
            device_status=lambda: {"connected": True, "connection": "preconfigured",
                                   "ip": "192.168.3.51"},
            networks=lambda: [{"ssid": "Cafe", "signal": 70, "security": "WPA2", "active": False}],
            wifi_profiles=lambda: [("preconfigured", "Home")],
            security_from_scan=wifi_net.security_from_scan,
            save=lambda net: calls.append(("save", net["ssid"], net["security"])) or net["ssid"],
            plan=lambda net: self.plan,
            activate=lambda name, ssid: calls.append(("up", name)) or ("connected", f"Connected to {ssid}."),
            forget=lambda name: (True, f"Removed {name}."))
        bt = types.SimpleNamespace(
            valid_mac=bt_admin.valid_mac,
            paired=lambda: [{"mac": "AA:BB:CC:DD:EE:FF", "name": "Buds", "icon": "audio-headset",
                             "paired": True, "connected": True, "earbuds": True}],
            earbuds=lambda: "AA:BB:CC:DD:EE:FF",
            scan=lambda seconds: [{"mac": "11:22:33:44:55:66", "name": "New buds", "icon": "audio-headset"}],
            pair=lambda mac: calls.append(("pair", mac)) or (True, "Paired and connected."),
            connect=lambda mac: (True, "Connected."),
            forget=lambda mac: (False, "The cane speaks through this device."),
            save_earbuds=lambda mac: calls.append(("save_earbuds", mac)))
        self.api = admin_api.AdminAPI(password_file=os.path.join(self.dir, "pw"),
                                      say=self.said.append, set_earbuds=self.ears.append,
                                      wifi=wifi, bt=bt, background=self.later.append)

    def call(self, path, body=None, headers=None, ip="127.0.0.1", session=None):
        import json
        h = dict(headers or self.SITE)
        if session:
            h["Authorization"] = "Bearer " + session
        method = "GET" if body is None else "POST"
        return self.api.handle(method, "/admin/api/" + path, h,
                               b"" if body is None else json.dumps(body).encode(), ip)

    def logged_in(self):
        code, r = self.call("setup", {"password": "correct horse"}, self.HOME, "192.168.3.13")
        self.assertEqual(code, 200, r)
        return r["session"]

    # -- password and sessions --

    def test_first_password_only_from_the_home_network(self):
        self.assertEqual(self.call("setup", {"password": "correct horse"})[0], 403)   # tunnel
        self.assertEqual(self.call("setup", {"password": "correct horse"}, self.HOME,
                                   "203.0.113.5")[0], 403)                           # not private
        self.assertEqual(self.call("status")[1]["password_set"], False)
        self.logged_in()
        self.assertEqual(self.call("setup", {"password": "another one"}, self.HOME,
                                   "192.168.3.13")[0], 409)

    def test_short_password_is_refused(self):
        self.assertEqual(self.call("setup", {"password": "short"}, self.HOME, "192.168.3.13")[0], 400)

    def test_password_file_holds_no_password(self):
        self.logged_in()
        with open(os.path.join(self.dir, "pw")) as fh:
            self.assertNotIn("correct horse", fh.read())
        if os.name == "posix":
            self.assertEqual(os.stat(os.path.join(self.dir, "pw")).st_mode & 0o777, 0o600)

    def test_login_logout_and_wrong_passwords(self):
        self.logged_in()
        self.assertEqual(self.call("login", {"password": "wrong one!"})[0], 401)
        code, r = self.call("login", {"password": "correct horse"})
        self.assertEqual(code, 200)
        s = r["session"]
        self.assertTrue(self.call("status", session=s)[1]["logged_in"])
        self.assertEqual(self.call("logout", {}, session=s)[0], 200)
        self.assertEqual(self.call("wifi", session=s)[0], 401)

    def test_five_wrong_passwords_pause_logins(self):
        self.logged_in()
        for _ in range(5):
            self.call("login", {"password": "wrong one!"})
        self.assertEqual(self.call("login", {"password": "correct horse"})[0], 429)

    def test_changing_the_password_logs_others_out(self):
        s1 = self.logged_in()
        s2 = self.call("login", {"password": "correct horse"})[1]["session"]
        self.assertEqual(self.call("password", {"old": "nope nope", "new": "brand new pw"}, session=s1)[0], 401)
        self.assertEqual(self.call("password", {"old": "correct horse", "new": "brand new pw"}, session=s1)[0], 200)
        self.assertEqual(self.call("wifi", session=s2)[0], 401)
        self.assertEqual(self.call("wifi", session=s1)[0], 200)
        self.assertEqual(self.call("login", {"password": "brand new pw"})[0], 200)

    def test_nothing_changes_without_login(self):
        self.logged_in()
        for path, body in (("wifi", None), ("wifi/join", {"ssid": "x"}), ("bt", None),
                           ("bt/pair", {"mac": "11:22:33:44:55:66"})):
            self.assertEqual(self.call(path, body)[0], 401, path)
        self.assertEqual(self.calls, [])

    # -- browser checks --

    def test_other_sites_and_rebinding_are_refused(self):
        s = self.logged_in()
        evil = dict(self.SITE, Origin="https://evil.example")
        self.assertEqual(self.call("wifi", headers=evil, session=s)[0], 403)
        rebound = {"Host": "evil.example:8080", "Origin": "http://evil.example:8080"}
        self.assertEqual(self.call("setup", {"password": "correct horse"}, rebound, "192.168.3.13")[0], 403)
        self.assertEqual(self.api.cors_headers(evil), {})
        self.assertEqual(self.api.cors_headers(self.SITE)["Access-Control-Allow-Origin"],
                         "https://adeliusa486.github.io")

    # -- Wi-Fi --

    def test_join_answers_first_then_switches(self):
        s = self.logged_in()
        code, r = self.call("wifi/join", {"ssid": "Cafe", "password": "hunter22", "security": "WPA2"},
                            session=s)
        self.assertEqual((code, r["code"]), (200, "joining"))
        self.assertEqual(self.calls, [("save", "Cafe", "wpa")])          # not joined yet
        self.later[0]()                                                   # the background part
        self.assertEqual(self.calls[-1], ("up", "Cafe"))
        self.assertEqual(self.said, ["Connected to Cafe."])
        self.assertNotIn("hunter22", str(r))

    def test_join_out_of_range_or_already_on_it(self):
        s = self.logged_in()
        self.plan = "away"
        self.assertEqual(self.call("wifi/join", {"ssid": "Cafe", "password": "hunter22"},
                                   session=s)[1]["code"], "away")
        self.plan = "already"
        self.assertEqual(self.call("wifi/join", {"ssid": "Cafe", "password": "hunter22"},
                                   session=s)[1]["code"], "already")
        self.assertEqual(self.later, [])

    def test_join_checks_its_input(self):
        s = self.logged_in()
        self.assertEqual(self.call("wifi/join", {"ssid": "", "password": "hunter22"}, session=s)[0], 400)
        self.assertEqual(self.call("wifi/join", {"ssid": "Cafe", "password": "short",
                                                 "security": "WPA2"}, session=s)[0], 400)
        r = self.call("wifi/join", {"ssid": "Work", "password": "x" * 9,
                                    "security": "WPA2 802.1X"}, session=s)[1]
        self.assertEqual(r["code"], "enterprise")
        self.call("wifi/join", {"ssid": "Free", "password": "", "security": "--"}, session=s)
        self.assertEqual(self.calls[-1], ("save", "Free", "open"))

    def test_wifi_status_marks_saved_networks(self):
        s = self.logged_in()
        w = self.call("wifi", session=s)[1]
        self.assertEqual((w["connection"], w["ssid"]), ("preconfigured", "Home"))
        self.assertEqual(w["networks"][0]["saved"], False)
        self.assertEqual(w["saved"], [{"name": "preconfigured", "ssid": "Home", "active": True}])

    # -- Bluetooth --

    def test_pairing_makes_it_the_earbuds(self):
        s = self.logged_in()
        r = self.call("bt/pair", {"mac": "11:22:33:44:55:66"}, session=s)[1]
        self.assertTrue(r["ok"])
        self.assertIn(("save_earbuds", "11:22:33:44:55:66"), self.calls)
        self.assertEqual(self.ears, ["11:22:33:44:55:66"])

    def test_bad_address_and_forgetting_the_earbuds(self):
        s = self.logged_in()
        self.assertEqual(self.call("bt/pair", {"mac": "not-a-mac"}, session=s)[0], 400)
        self.assertFalse(self.call("bt/forget", {"mac": "AA:BB:CC:DD:EE:FF"}, session=s)[1]["ok"])

    # -- the real server --

    def test_server_serves_page_preflight_and_api(self):
        import json
        import socket
        import urllib.error
        import urllib.request
        import demo_server
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        d = demo_server.DemoServer(port, os.path.join(assistant.SHM, "nothing.jpg"),
                                   host="127.0.0.1", admin=self.api)
        httpd = d.start()
        try:
            url = f"http://127.0.0.1:{port}"
            self.assertIn("OmniWalk Admin", urllib.request.urlopen(url + "/admin").read().decode())
            site = {"Origin": "https://adeliusa486.github.io"}
            r = urllib.request.urlopen(urllib.request.Request(
                url + "/admin/api/login", method="OPTIONS", headers=dict(
                    site, **{"Access-Control-Request-Method": "POST",
                             "Access-Control-Request-Headers": "authorization, content-type"})))
            self.assertEqual(r.status, 204)
            self.assertEqual(r.headers["Access-Control-Allow-Origin"], site["Origin"])
            self.assertIn("Authorization", r.headers["Access-Control-Allow-Headers"])
            st = json.loads(urllib.request.urlopen(urllib.request.Request(
                url + "/admin/api/status", headers=site)).read())
            self.assertEqual((st["password_set"], st["local"]), (False, False))   # 127.0.0.1 = tunnel
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(urllib.request.Request(url + "/admin/api/wifi", headers=site))
            self.assertEqual(e.exception.code, 401)
            self.assertEqual(e.exception.headers["Access-Control-Allow-Origin"], site["Origin"])
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(urllib.request.Request(
                    url + "/admin/api/status", headers={"Origin": "https://evil.example"}))
            self.assertEqual(e.exception.code, 403)
            self.assertIsNone(e.exception.headers["Access-Control-Allow-Origin"])
        finally:
            httpd.shutdown()
            httpd.server_close()


class SetupHotspot(unittest.TestCase):
    """No known Wi-Fi for a while: the cane opens OmniWalk-Setup, and closes it
    again to look for known networks."""

    def make(self, phones=0):
        import types
        import wifi_hotspot
        self.H = wifi_hotspot
        self.t = 0.0
        self.st = {"connected": True, "connection": "preconfigured", "ip": ""}
        self.log = []

        def up():
            self.log.append("up")
            self.st.update(connected=True, connection="OmniWalk-Setup")
            return True

        def down():
            self.log.append("down")
            self.st.update(connected=False, connection="")
            return True
        wifi = types.SimpleNamespace(HOTSPOT="OmniWalk-Setup", device_status=lambda: dict(self.st),
                                     hotspot_up=up, hotspot_down=down)
        return wifi_hotspot.Manager(wifi=wifi, clock=lambda: self.t, phones=lambda: phones)

    def run_for(self, m, seconds):
        end = self.t + seconds
        while self.t < end:
            m.step()
            self.t += 5

    def test_on_wifi_nothing_happens(self):
        m = self.make()
        self.run_for(m, 600)
        self.assertEqual(self.log, [])

    def test_hotspot_after_90_s_without_wifi_then_a_new_search(self):
        m = self.make()
        self.st.update(connected=False, connection="")
        self.run_for(m, 85)
        self.assertEqual(self.log, [])
        self.run_for(m, 10)
        self.assertEqual(self.log, ["up"])
        self.run_for(m, self.H.HOTSPOT_MIN_S)
        self.assertEqual(self.log, ["up", "down"])          # nobody on it

    def test_a_phone_on_the_hotspot_keeps_it_open(self):
        m = self.make(phones=1)
        self.st.update(connected=False, connection="")
        self.run_for(m, 95)
        self.run_for(m, self.H.HOTSPOT_MIN_S + 60)
        self.assertEqual(self.log, ["up"])
        self.run_for(m, self.H.HOTSPOT_MAX_S)
        self.assertEqual(self.log[:2], ["up", "down"])       # but not for ever

    def test_joining_a_network_from_the_hotspot_ends_it(self):
        m = self.make()
        self.st.update(connected=False, connection="")
        self.run_for(m, 95)
        self.st.update(connected=True, connection="Cafe")
        self.assertEqual(m.step(), "connected")
        self.assertIsNone(m.hotspot_since)


if __name__ == "__main__":
    unittest.main(verbosity=2)
