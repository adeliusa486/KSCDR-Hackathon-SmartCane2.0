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
  - assistant button: press = describe, double = read text, hold = ask,
    and every failure (no internet, no key, no mic, no camera) says something
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
    LABELS = r"D:\smartcane-data\hailo\smartcane152.txt"

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

    def test_buzz_stronger_when_closer(self):
        self.assertEqual(sd.tof_buzz(2000), "B80,200")
        self.assertEqual(sd.tof_buzz(300), "B100,450")
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
            threading.Thread(target=w.run, daemon=True).start()
            time.sleep(3.6)                        # no D lines, past start-up grace
            stop.set()
            self.assertIn("Warning, distance sensors not responding", s.heard)
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
        self.feed("D 1000 640 1350 1 1 1300")      # and it still reads after
        self.assertEqual(self.link.fwd_mm, 640)


class AssistantButton(unittest.TestCase):
    """Button timing and every failure path, with Gemini and the mic faked."""

    class Mic:
        def __init__(self, ok=True, seconds=2.0):
            self.ok, self.seconds = ok, seconds

        def start(self):
            if self.ok:
                with open(assistant.QUESTION_WAV, "wb") as fh:
                    fh.write(b"\0" * int(32000 * self.seconds))
            return self.ok

        def stop(self):
            pass

    def make(self, mic=None, jpeg=b"\xff\xd8fake", reply=None, error=None,
             key="k"):
        self.said, self.prompts = [], []
        a = assistant.Assistant(lambda: jpeg, lambda: "car left",
                                self.said.append, "00:00:00:00:00:00",
                                mic=mic or self.Mic())

        def fake(k, prompt, j, wav, ctx):
            self.prompts.append((prompt, wav is not None))
            if error:
                raise RuntimeError(error)
            return reply or "A clear pavement ahead."
        self._orig = (assistant.gemini, assistant.load_key, assistant.ocr_offline)
        assistant.gemini = fake
        assistant.load_key = lambda: key
        assistant.ocr_offline = lambda j: "Offline reading. EXIT"
        return a

    def tearDown(self):
        assistant.gemini, assistant.load_key, assistant.ocr_offline = self._orig

    def press(self, a, hold):
        a.on_button(True)
        time.sleep(hold)
        a.on_button(False)

    def settle(self, a, t=1.5):
        time.sleep(t)
        a.busy.acquire(timeout=5)
        a.busy.release()

    def test_short_press_describes(self):
        a = self.make()
        self.press(a, 0.1)
        self.settle(a)
        self.assertEqual(self.prompts, [(assistant.DESCRIBE, False)])
        self.assertEqual(self.said, ["Looking", "A clear pavement ahead."])

    def test_double_press_reads_text(self):
        a = self.make(reply="Exit")
        self.press(a, 0.1)
        time.sleep(0.15)
        self.press(a, 0.1)
        self.settle(a)
        self.assertEqual(self.prompts, [(assistant.READ, False)])
        self.assertEqual(self.said, ["Reading", "Exit"])

    def test_hold_asks_with_audio(self):
        a = self.make(reply="It is a bus stop.")
        self.press(a, 1.2)
        self.settle(a)
        self.assertEqual(self.prompts, [(assistant.ASK, True)])
        self.assertEqual(self.said[-1], "It is a bus stop.")

    def test_hold_with_no_mic_still_describes(self):
        a = self.make(mic=self.Mic(ok=False))
        self.press(a, 1.0)
        self.settle(a)
        self.assertEqual(self.prompts, [(assistant.DESCRIBE, False)])
        self.assertIn("I could not hear a question, describing instead", self.said)

    def test_too_short_question_is_not_sent_as_audio(self):
        a = self.make(mic=self.Mic(seconds=0.1))
        self.press(a, 0.8)
        self.settle(a)
        self.assertEqual(self.prompts, [(assistant.DESCRIBE, False)])

    def test_no_internet_is_spoken(self):
        a = self.make(error="no internet, assistant unavailable")
        self.press(a, 0.1)
        self.settle(a)
        self.assertEqual(self.said[-1], "no internet, assistant unavailable")

    def test_read_text_offline_falls_back_to_ocr(self):
        a = self.make(error="no internet, assistant unavailable")
        self.press(a, 0.1); time.sleep(0.15); self.press(a, 0.1)
        self.settle(a)
        self.assertEqual(self.said[-1], "Offline reading. EXIT")

    def test_busy_service_retries_once(self):
        a = self.make(error="assistant busy, try again")
        self.press(a, 0.1)
        self.settle(a, 4.0)
        self.assertEqual(len(self.prompts), 2)
        self.assertIn("Still looking", self.said)

    def test_no_key_is_spoken(self):
        a = self.make(key="")
        self.press(a, 0.1)
        self.settle(a)
        self.assertEqual(self.said[-1], "Assistant key missing")

    def test_camera_failure_is_spoken(self):
        a = self.make(jpeg=None)
        self.press(a, 0.1)
        self.settle(a)
        self.assertEqual(self.said[-1], "Camera not ready")

    def test_presses_during_an_answer_are_ignored(self):
        a = self.make()
        a.busy.acquire()
        try:
            self.press(a, 0.1)
            time.sleep(0.8)
        finally:
            a.busy.release()
        self.assertEqual(self.prompts, [])


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
            self.assertIn(b"Smart Cane", page)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
