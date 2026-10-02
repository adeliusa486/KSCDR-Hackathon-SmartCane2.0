"""Stand-in for picamera2, for laptop tests of detect.py only.

Delivers frames at the configured frame rate with a SensorTimestamp a fixed
40 ms before the frame is returned, on CLOCK_BOOTTIME, so tests can check
that the trace and its summary recover that delay.
"""
import time

FAKE_SENSOR_DELAY_NS = 40_000_000


class _Request:
    def __init__(self, size, sensor_ts):
        self.size = size
        self.sensor_ts = sensor_ts

    def make_array(self, stream):
        w, h = self.size
        return bytearray(w * h * 3)

    def get_metadata(self):
        return {"SensorTimestamp": self.sensor_ts, "ExposureTime": 33000,
                "AnalogueGain": 2.0}

    def release(self):
        pass


class Picamera2:
    camera_properties = {"Model": "fake", "PixelArraySize": (4608, 2592)}

    def __init__(self):
        self.fps = 15
        self.lores = (640, 640)
        self.next_frame = 0

    def create_preview_configuration(self, main, lores, controls):
        return {"main": main, "lores": lores, "controls": controls}

    def configure(self, config):
        self.fps = config["controls"].get("FrameRate", 15)
        self.lores = config["lores"]["size"]

    def start(self):
        self.next_frame = time.monotonic()

    def start_preview(self):
        pass

    def stop(self):
        pass

    def capture_request(self):
        # A real camera holds a few buffers and drops the rest, so a reader
        # that falls behind (detect.py sleeps 1.5 s after start) does not
        # get a burst of old frames. Resync instead of queueing.
        now = time.monotonic()
        if self.next_frame < now - 1.0 / self.fps:
            self.next_frame = now
        self.next_frame += 1.0 / self.fps
        wait = self.next_frame - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        ts = time.clock_gettime_ns(time.CLOCK_BOOTTIME) - FAKE_SENSOR_DELAY_NS
        return _Request(self.lores, ts)
