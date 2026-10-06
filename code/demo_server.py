"""Smart cane - live demo dashboard for a laptop browser.

Runs inside speak_detect.py with --demo-port. Open http://smartcane.local:8080
(or the Pi's IP) on any laptop on the same network:

    /             the dashboard (demo_dashboard.html, no internet needed)
    /stream.mjpg  camera with detections drawn, from detect.py --stream-file
    /events       server-sent events, 4 per second: detections, fps, ToF
                  distances, ground state, temperature, everything spoken

Standard library only. Each browser tab costs one thread and ~10 fps of JPEGs
that are already encoded, so several laptops can watch at once.
"""
import collections
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))


def cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as fh:
            return round(int(fh.read()) / 1000, 1)
    except OSError:
        return None


class DemoServer:
    def __init__(self, port, view_path, esp=None, model="", n_classes=0):
        self.port = port
        self.view_path = view_path
        self.json_path = os.path.splitext(view_path)[0] + ".json"
        self.esp = esp
        self.model = os.path.basename(model or "")
        self.n_classes = n_classes
        self.started = time.time()
        self.said = collections.deque(maxlen=14)
        self.seq = 0
        self.lock = threading.Lock()

    # Called by the speaker for every sentence actually spoken.
    def spoken(self, text, kind="speech"):
        with self.lock:
            self.seq += 1
            self.said.append({"id": self.seq, "t": time.time(),
                              "text": text, "kind": kind})

    def state(self):
        try:
            with open(self.json_path) as fh:
                vision = json.load(fh)
            age = time.time() - os.path.getmtime(self.json_path)
        except (OSError, ValueError):
            vision, age = {"fps": 0, "infer_ms": 0, "dets": []}, 99
        esp = self.esp
        sensors = None
        if esp is not None:
            sensors = {
                "alive": esp.alive(within=1.0),
                "fwd_mm": esp.fwd_mm if esp.fwd_ok else None,
                "down_mm": esp.down_mm if esp.down_ok else None,
                "ground_mm": esp.ground_mm,
                "fwd_ok": esp.fwd_ok, "down_ok": esp.down_ok,
            }
        with self.lock:
            said = list(self.said)
        return {"vision": vision, "vision_age": round(age, 2),
                "sensors": sensors, "said": said, "temp": cpu_temp(),
                "uptime": int(time.time() - self.started),
                "model": self.model, "classes": self.n_classes}

    def start(self):
        server = self
        page = os.path.join(HERE, "demo_dashboard.html")

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path in ("/", "/index.html"):
                    with open(page, "rb") as fh:
                        body = fh.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path.startswith("/stream.mjpg"):
                    self._mjpeg()
                elif self.path.startswith("/events"):
                    self._events()
                else:
                    self.send_error(404)

            def _mjpeg(self):
                self.send_response(200)
                self.send_header("Content-Type",
                                 "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                last = 0
                try:
                    while True:
                        try:
                            m = os.path.getmtime(server.view_path)
                        except OSError:
                            time.sleep(0.2)
                            continue
                        if m == last:
                            time.sleep(0.02)
                            continue
                        last = m
                        with open(server.view_path, "rb") as fh:
                            jpg = fh.read()
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n"
                                         + f"Content-Length: {len(jpg)}\r\n\r\n".encode()
                                         + jpg + b"\r\n")
                except (ConnectionError, OSError):
                    pass

            def _events(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                try:
                    while True:
                        data = json.dumps(server.state())
                        self.wfile.write(f"data: {data}\n\n".encode())
                        self.wfile.flush()
                        time.sleep(0.25)
                except (ConnectionError, OSError):
                    pass

        httpd = ThreadingHTTPServer(("0.0.0.0", self.port), Handler)
        httpd.daemon_threads = True
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd
