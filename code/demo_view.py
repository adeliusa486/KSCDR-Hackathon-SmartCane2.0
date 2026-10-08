"""Smart cane - demo view: the camera frame with the cane's detections drawn.

Used by detect.py only with --stream-file. Writes a JPEG and a JSON of the
detections to RAM (/dev/shm). demo_server.py, in the speech process, serves
them to the live dashboard. Both files are written to a temp name and
renamed, so the server never reads half a frame.

Each detection in the JSON carries what the dashboard needs to show real
boxes with real distances: the box (fractions of the frame), the bearing in
degrees, left / ahead / right, the camera's distance estimate in metres, and
the confidence. The forward ToF reading comes separately from the ESP32, and
the dashboard puts the two side by side for the object straight ahead.

At most MAX_FPS frames a second are drawn, and only while someone has the
dashboard open: demo_server.py touches <path>.watch on every request, and
frames stop WATCH_S seconds after the last one. JPEG encoding on the Pi's CPU
is the cost (about 73 % of a core at 10 fps on 8 Oct 2026), so with nobody
watching the cane runs as if the dashboard were off. The Hailo path is
untouched.
"""
import json
import math
import os
import time

from PIL import Image, ImageDraw, ImageFont

OUT_W, OUT_H = 960, 540
MAX_FPS = 6.0
WATCH_S = 5.0

# Colour says how dangerous, the same order the cane speaks in.
DROP = {"open hole", "stairs", "pothole", "manhole", "curb", "rail track",
        "storm drain", "swimming pool", "escalator"}
MOVING = {"car", "bus", "truck", "van", "taxi", "ambulance", "motorcycle",
          "bicycle", "e-scooter", "train", "cyclist", "motorcyclist",
          "golf cart", "trailer", "skateboard"}
LIVING = {"person", "child", "dog", "cat", "cow", "horse", "wheelchair",
          "stroller", "bird", "sheep", "goat", "camel"}
BLOCK = {"traffic cone", "barrier", "bollard", "pole", "utility pole",
         "fence", "bench", "pillar", "fire hydrant", "trash can"}

RED, ORANGE, YELLOW, PURPLE, CYAN = ((255, 69, 58), (255, 159, 10),
                                     (255, 214, 10), (191, 90, 242),
                                     (64, 200, 224))


def colour(label):
    if label in DROP:
        return RED, "drop"
    if label in MOVING:
        return ORANGE, "vehicle"
    if label in LIVING:
        return YELLOW, "living"
    if label in BLOCK:
        return PURPLE, "obstacle"
    return CYAN, "object"


def _font(size):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


class Viewer:
    def __init__(self, path, width, height, hfov, corridor, info):
        """info(det) -> dict with zone, near, est_m and bearing for one
        detection, from detect.py's own geometry."""
        self.path = path
        self.json_path = os.path.splitext(path)[0] + ".json"
        self.watch_path = path + ".watch"
        self.w, self.h = width, height
        self.hfov, self.corridor = hfov, corridor
        self.info = info
        self.font = _font(17)
        self.last = 0.0
        self.frame_id = 0
        # A camera mounted on its side gives an upright portrait picture.
        self.out = (OUT_W, OUT_H) if width >= height else (OUT_H, OUT_W)
        self.sx, self.sy = self.out[0] / width, self.out[1] / height
        # Edges of the 'ahead' walking corridor, drawn as two faint lines so
        # viewers see why something is called left, ahead or right.
        half = math.tan(math.radians(hfov / 2))
        off = math.tan(math.radians(corridor)) / (2 * half)
        self.lanes = [self.out[0] * (0.5 - off), self.out[0] * (0.5 + off)]

    def due(self):
        """True when the next frame should be drawn: the dashboard asked for
        one in the last WATCH_S seconds and MAX_FPS is not exceeded."""
        if time.monotonic() - self.last < 1.0 / MAX_FPS:
            return False
        try:
            return time.time() - os.path.getmtime(self.watch_path) < WATCH_S
        except OSError:
            return False

    def write(self, frame, dets, fps, infer_ms):
        self.last = time.monotonic()
        self.frame_id += 1
        # picamera2 XRGB8888 arrives as B, G, R, X bytes.
        img = Image.fromarray(frame[:, :, [2, 1, 0]]).resize(self.out,
                                                            Image.BILINEAR)
        out_w, out_h = self.out
        d = ImageDraw.Draw(img, "RGBA")
        for x in self.lanes:
            d.line([(x, out_h * 0.35), (x, out_h)], fill=(255, 255, 255, 70), width=2)
        out = []
        for det in dets[:8]:
            col, kind = colour(det.label)
            meta = self.info(det)
            x0, y0 = det.x0 * self.sx, det.y0 * self.sy
            x1, y1 = det.x1 * self.sx, det.y1 * self.sy
            d.rectangle([x0, y0, x1, y1], fill=col + (26,))
            # Corner brackets read as "tracked object" better than a full box.
            k = max(10, min(28, (x1 - x0) / 4, (y1 - y0) / 4))
            for (cx, cy, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1),
                                     (x0, y1, 1, -1), (x1, y1, -1, -1)):
                d.line([(cx, cy), (cx + dx * k, cy)], fill=col + (255,), width=4)
                d.line([(cx, cy), (cx, cy + dy * k)], fill=col + (255,), width=4)
            d.rectangle([x0, y0, x1, y1], outline=col + (150,), width=1)
            est = meta.get("est_m")
            text = f"{det.label}  {det.score:.0%}" + (f"  ~{est:.1f} m" if est else "")
            tw = d.textlength(text, font=self.font)
            ty = y0 - 26 if y0 >= 26 else y1 + 2
            tx = min(max(0, x0), out_w - tw - 12)
            d.rectangle([tx, ty, tx + tw + 12, ty + 24], fill=col + (235,))
            d.text((tx + 6, ty + 3), text, fill=(0, 0, 0), font=self.font)
            out.append({
                "label": det.label, "score": round(det.score, 3), "kind": kind,
                "zone": meta.get("zone"), "near": meta.get("near"),
                "est_m": round(est, 2) if est else None,
                "bearing": round(meta.get("bearing", 0.0), 1),
                "box": [round(det.x0 / self.w, 4), round(det.y0 / self.h, 4),
                        round(det.x1 / self.w, 4), round(det.y1 / self.h, 4)],
            })
        tmp = self.path + ".tmp"
        img.save(tmp, "JPEG", quality=72)
        os.replace(tmp, self.path)
        tmp = self.json_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"frame": self.frame_id, "t": time.time(),
                       "fps": round(fps, 1), "infer_ms": round(infer_ms, 1),
                       "hfov": round(self.hfov, 1), "corridor": self.corridor,
                       "size": [out_w, out_h], "dets": out}, fh)
        os.replace(tmp, self.json_path)
