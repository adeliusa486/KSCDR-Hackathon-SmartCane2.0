"""Smart cane - live dashboard server.

Runs inside speak_detect.py with --demo-port. Open http://smartcane.local:8080
(or the Pi's IP) on any laptop on the same network, or the public tunnel
address (docs/deployment.md) from anywhere:

    /             the dashboard (demo_dashboard.html, no internet needed)
    /frame.jpg    the latest camera frame with detections drawn. Its id is in
                  the X-Frame header. With ?after=<id> the request waits up
                  to FRAME_WAIT_S for a newer frame (204 if none), so
                  polling gets each frame once, as soon as it is drawn
    /state.json   detections with boxes, bearings and camera distances, fps,
                  ToF distances, ground state, temperature, everything spoken
    /stream.mjpg  the frames as one MJPEG stream (for VLC or a plain <img>)
    /events       the state as server-sent events, 4 per second
    /health       "ok", for tunnel and uptime checks
    /admin        the owner's control page (admin_dashboard.html): live view,
                  Wi-Fi, Bluetooth. Its API, /admin/api/..., is admin_api.py
                  and needs the admin password whatever the token says.

The dashboard itself polls /state.json and /frame.jpg. Tunnels such as
Cloudflare's hold long-lived streams back (tested: /events delivered 0 bytes
in 6 s through a quick tunnel), while single requests pass at once. The two
stream endpoints stay for local use.

With --demo-token every URL except /health needs ?token=<token> (the
dashboard passes it on by itself). Use a token whenever the dashboard is
reachable from the internet: it shows the camera.

Cross-origin reads are allowed (Access-Control-Allow-Origin: *) so the
project website can show the live feed from another address. The token, not
the origin, decides who gets in.

Standard library only. Each browser tab costs one thread and the frames that
are already encoded, so several laptops can watch at once. Frames are drawn
only while a request arrived in the last few seconds (see touch()), so the
server can stay on all the time.
"""
import collections
import hmac
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
FRAME_WAIT_S = 2.0


def cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as fh:
            return round(int(fh.read()) / 1000, 1)
    except OSError:
        return None


class DemoServer:
    def __init__(self, port, view_path, esp=None, model="", n_classes=0,
                 token="", host="0.0.0.0", admin=None):
        self.port = port
        self.host = host
        self.view_path = view_path
        self.json_path = os.path.splitext(view_path)[0] + ".json"
        # demo_view.Viewer.due() draws frames only while this file is fresh.
        self.watch_path = view_path + ".watch"
        self._touched = 0.0
        self.esp = esp
        self.model = os.path.basename(model or "")
        self.n_classes = n_classes
        self.token = token or ""
        self.admin = admin               # admin_api.AdminAPI, or None
        self.started = time.time()
        self.frame_wait = FRAME_WAIT_S
        self.said = collections.deque(maxlen=14)
        self.seq = 0
        self.lock = threading.Lock()

    def touch(self):
        """Someone is watching: tell detect.py to keep drawing frames."""
        now = time.monotonic()
        if now - self._touched < 1.0:
            return
        self._touched = now
        try:
            with open(self.watch_path, "a"):
                pass
            os.utime(self.watch_path)
        except OSError:
            pass

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
                "uptime": int(time.time() - self.started), "t": time.time(),
                "model": self.model, "classes": self.n_classes}

    def allowed(self, query):
        if not self.token:
            return True
        given = parse_qs(query).get("token", [""])[0]
        return hmac.compare_digest(given.encode(), self.token.encode())

    def start(self):
        server = self
        page = os.path.join(HERE, "demo_dashboard.html")
        admin_page = os.path.join(HERE, "admin_dashboard.html")

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            # ---- admin: its own CORS (the website only), never "*" -------
            def _admin(self, method, path):
                if server.admin is None:
                    return self._send(404, "text/plain", b"no admin page on this cane")
                body = b""
                if method == "POST":
                    n = int(self.headers.get("Content-Length") or 0)
                    if n > 65536:
                        return self._send(413, "text/plain", b"too large")
                    body = self.rfile.read(n)
                code, data = server.admin.handle(method, path, self.headers, body,
                                                 self.client_address[0])
                out = json.dumps(data).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(out)))
                for k, v in server.admin.cors_headers(self.headers).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(out)

            def do_OPTIONS(self):
                cors = server.admin.cors_headers(self.headers) if server.admin else {}
                if not urlsplit(self.path).path.startswith("/admin/api/") or not cors:
                    self.send_response(403)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(204)
                for k, v in cors.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_POST(self):
                path = urlsplit(self.path).path
                if path.startswith("/admin/api/"):
                    return self._admin("POST", path)
                self.send_error(404)

            def _headers(self, code, ctype, length=None, frame=None):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache, no-store")
                if frame is not None:
                    self.send_header("X-Frame", frame)
                    self.send_header("Access-Control-Expose-Headers", "X-Frame")
                if length is not None:
                    self.send_header("Content-Length", str(length))
                self.end_headers()

            def _send(self, code, ctype, body, frame=None):
                self._headers(code, ctype, len(body), frame)
                self.wfile.write(body)

            def do_GET(self):
                url = urlsplit(self.path)
                path = url.path
                if path == "/health":
                    return self._send(200, "text/plain", b"ok")
                if path.startswith("/admin/api/"):
                    return self._admin("GET", path)
                if path in ("/admin", "/admin/", "/admin.html"):
                    with open(admin_page, "rb") as fh:
                        return self._send(200, "text/html; charset=utf-8", fh.read())
                if not server.allowed(url.query):
                    return self._send(403, "text/plain",
                                      b"token required: add ?token=... to the address")
                server.touch()
                if path in ("/", "/index.html"):
                    with open(page, "rb") as fh:
                        self._send(200, "text/html; charset=utf-8", fh.read())
                elif path == "/stream.mjpg":
                    self._mjpeg()
                elif path == "/events":
                    self._events()
                elif path == "/state.json":
                    self._send(200, "application/json",
                               json.dumps(server.state()).encode())
                elif path == "/frame.jpg":
                    self._frame(parse_qs(url.query).get("after", [""])[0])
                else:
                    self.send_error(404)

            def _frame(self, after):
                # The id is the file's write time in microseconds, read from
                # the open file, so id and picture always belong together
                # (each frame is a new file, renamed into place).
                deadline = time.monotonic() + server.frame_wait
                while True:
                    try:
                        with open(server.view_path, "rb") as fh:
                            fid = str(os.fstat(fh.fileno()).st_mtime_ns // 1000)
                            if fid != after:
                                return self._send(200, "image/jpeg", fh.read(), fid)
                    except OSError:
                        return self._send(503, "text/plain", b"no frame yet")
                    if time.monotonic() > deadline:
                        return self._send(204, "image/jpeg", b"", fid)
                    server.touch()
                    time.sleep(0.02)

            def _mjpeg(self):
                self._headers(200, "multipart/x-mixed-replace; boundary=frame")
                last = 0
                try:
                    while True:
                        try:
                            m = os.path.getmtime(server.view_path)
                        except OSError:
                            time.sleep(0.2)
                            continue
                        server.touch()
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
                self._headers(200, "text/event-stream")
                try:
                    while True:
                        server.touch()
                        data = json.dumps(server.state())
                        self.wfile.write(f"data: {data}\n\n".encode())
                        self.wfile.flush()
                        time.sleep(0.25)
                except (ConnectionError, OSError):
                    pass

        httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        httpd.daemon_threads = True
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd
