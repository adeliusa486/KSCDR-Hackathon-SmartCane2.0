"""Stand-in for picamera2.devices.Hailo: 13 ms per inference, one person."""
import time

FAKE_INFERENCE_S = 0.013


class Hailo:
    def __init__(self, model):
        self.model = model

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_input_shape(self):
        return (640, 640, 3)

    def run(self, frame):
        time.sleep(FAKE_INFERENCE_S)
        out = [[] for _ in range(80)]
        out[0] = [[0.2, 0.45, 0.9, 0.55, 0.87]]   # person, ahead
        return out
