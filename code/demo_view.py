"""Smart cane - demo view: the camera frame with the cane's detections drawn.

Used by detect.py only with --stream-file. Writes a JPEG and a JSON of the
detections to RAM (/dev/shm) every frame. demo_server.py, in the speech
process, serves them to the laptop. Both files are written to a temp name
and renamed, so the server never reads half a frame.

Costs ~15-25 ms per frame on the Pi 5 CPU, which fits inside the 100 ms frame
budget at 10 fps. The Hailo path is untouched.
"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

OUT_W, OUT_H = 960, 540

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

RED, ORANGE, YELLOW, PURPLE, CYAN = ((255, 59, 48), (255, 149, 0),
                                     (255, 214, 10), (191, 90, 242),
                                     (50, 215, 230))


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
    def __init__(self, path, width, height, hfov, corridor, zone, nearness):
        self.path = path
        self.json_path = os.path.splitext(path)[0] + ".json"
        self.w, self.h = width, height
        self.hfov, self.corridor = hfov, corridor
        self.zone, self.nearness = zone, nearness
        self.font = _font(18)
        self.sx, self.sy = OUT_W / width, OUT_H / height
        # Edges of the 'ahead' walking corridor, drawn as two faint lines so
        # the audience sees why something is called left, ahead or right.
        import math
        half = math.tan(math.radians(hfov / 2))
        off = math.tan(math.radians(corridor)) / (2 * half)
        self.lanes = [OUT_W * (0.5 - off), OUT_W * (0.5 + off)]

    def write(self, frame, dets, fps, infer_ms):
        # picamera2 XRGB8888 arrives as B, G, R, X bytes.
        img = Image.fromarray(frame[:, :, [2, 1, 0]]).resize((OUT_W, OUT_H),
                                                            Image.BILINEAR)
        d = ImageDraw.Draw(img, "RGBA")
        for x in self.lanes:
            d.line([(x, OUT_H * 0.35), (x, OUT_H)], fill=(255, 255, 255, 70), width=2)
        out = []
        for det in dets[:8]:
            col, kind = colour(det.label)
            x0, y0 = det.x0 * self.sx, det.y0 * self.sy
            x1, y1 = det.x1 * self.sx, det.y1 * self.sy
            d.rectangle([x0, y0, x1, y1], outline=col + (255,), width=3)
            d.rectangle([x0, y0, x1, y1], fill=col + (28,))
            text = f"{det.label} {det.score:.0%}"
            tw = d.textlength(text, font=self.font)
            ty = max(0, y0 - 24)
            d.rectangle([x0, ty, x0 + tw + 10, ty + 24], fill=col + (235,))
            d.text((x0 + 5, ty + 2), text, fill=(0, 0, 0), font=self.font)
            out.append({
                "label": det.label, "score": round(det.score, 3), "kind": kind,
                "zone": self.zone(det.x0, det.x1, self.w, self.hfov, self.corridor),
                "near": self.nearness(det.y0, det.y1, self.h),
            })
        tmp = self.path + ".tmp"
        img.save(tmp, "JPEG", quality=72)
        os.replace(tmp, self.path)
        tmp = self.json_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"fps": round(fps, 1), "infer_ms": round(infer_ms, 1),
                       "dets": out}, fh)
        os.replace(tmp, self.json_path)
