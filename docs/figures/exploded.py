#!/usr/bin/env python3
"""Exploded view of the smart cane, drawn as an isometric technical
illustration with every part separate, numbered and listed.

    python docs/figures/exploded.py        # writes exploded_view.svg

Board outlines, chips, ports and headers use the manufacturers' published
sizes (Raspberry Pi 5 85 x 56 mm, AI HAT+ 65 x 56.5 mm, ESP32 DevKit V1
51 x 28 mm, VL53L0X breakout 25 x 10.7 mm, camera board 25 x 24 mm). The
3D-printed housing has no published CAD file and the power bank model is not
known, so those two are drawn to representative sizes. Not to scale between
the shortened cane shaft and the electronics.
"""
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
C30, S30 = math.cos(math.radians(30)), math.sin(math.radians(30))
FONT = "Segoe UI, Helvetica, Arial, sans-serif"
INK, INK2, MUTED, LINE = "#0f172a", "#475569", "#64748b", "#94a3b8"


def shade(hex_col, f):
    """f > 0 lightens towards white, f < 0 darkens towards black."""
    r, g, b = (int(hex_col[i:i + 2], 16) for i in (1, 3, 5))
    if f >= 0:
        r, g, b = (round(c + (255 - c) * f) for c in (r, g, b))
    else:
        r, g, b = (round(c * (1 + f)) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def hull(pts):
    pts = sorted(set((round(x, 2), round(y, 2)) for x, y in pts))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


class Part:
    """One component drawn at canvas position (ox, oy), local units in mm.
    x runs right-down, y left-down, z up (standard isometric)."""

    def __init__(self, ox, oy, k):
        self.ox, self.oy, self.k = ox, oy, k
        self.svg = []
        self.pts = []
        self.anchor = None

    def p(self, x, y, z):
        q = (self.ox + (x - y) * C30 * self.k, self.oy + (x + y) * S30 * self.k - z * self.k)
        self.pts.append(q)
        return q

    def poly(self, pts, fill, stroke=INK, sw=0.9, extra=""):
        self.svg.append('<polygon points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                        + f'" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" '
                          f'stroke-linejoin="round" {extra}/>')

    def box(self, x, y, z, w, d, h, col, sw=0.9):
        x1, y1, z1 = x + w, y + d, z + h
        P = self.p
        self.poly([P(x1, y, z), P(x1, y1, z), P(x1, y1, z1), P(x1, y, z1)], shade(col, -0.18), sw=sw)
        self.poly([P(x, y1, z), P(x1, y1, z), P(x1, y1, z1), P(x, y1, z1)], shade(col, -0.32), sw=sw)
        self.poly([P(x, y, z1), P(x1, y, z1), P(x1, y1, z1), P(x, y1, z1)], col, sw=sw)

    def rect_top(self, x, y, z, w, d, col, stroke="none", sw=0.6):
        P = self.p
        self.poly([P(x, y, z), P(x + w, y, z), P(x + w, y + d, z), P(x, y + d, z)], col, stroke, sw)

    def circle_pts(self, cx, cy, cz, r, axis="z", n=40):
        out = []
        for i in range(n):
            a = 2 * math.pi * i / n
            u, v = r * math.cos(a), r * math.sin(a)
            out.append({"z": (cx + u, cy + v, cz), "x": (cx, cy + u, cz + v),
                        "y": (cx + u, cy, cz + v)}[axis])
        return out

    def circle_top(self, cx, cy, z, r, col, stroke="none", sw=0.6):
        self.poly([self.p(*q) for q in self.circle_pts(cx, cy, z, r)], col, stroke, sw)

    def cylinder(self, cx, cy, cz, r, length, col, axis="z", sw=0.9):
        """Base centre (cx, cy, cz), extending `length` along +axis."""
        dx, dy, dz = {"z": (0, 0, length), "x": (length, 0, 0), "y": (0, length, 0)}[axis]
        a = self.circle_pts(cx, cy, cz, r, axis)
        b = self.circle_pts(cx + dx, cy + dy, cz + dz, r, axis)
        pa = [self.p(*q) for q in a]
        pb = [self.p(*q) for q in b]
        self.poly(hull(pa + pb), shade(col, -0.25), sw=sw)
        self.poly(pb, col, sw=sw)            # the +axis cap faces the viewer

    def text_top(self, x, y, z, txt, size, col="#ffffff", weight=600):
        """Silkscreen-style text lying on a top face."""
        X, Y = self.p(x, y, z)
        k = self.k
        self.svg.append(
            f'<text transform="matrix({C30 * k / 10:.4f},{S30 * k / 10:.4f},{-C30 * k / 10:.4f},'
            f'{S30 * k / 10:.4f},{X:.1f},{Y:.1f})" font-family="{FONT}" font-size="{size * 10:.1f}" '
            f'font-weight="{weight}" fill="{col}">{txt}</text>')

    def bbox(self):
        xs = [x for x, _ in self.pts]
        ys = [y for _, y in self.pts]
        return min(xs), min(ys), max(xs), max(ys)


# ---- components (local mm, origin at the board's back corner) --------------

PCB_GREEN, PCB_BLUE, PCB_BLACK, PCB_PURPLE = "#2f7d4c", "#24538f", "#262b33", "#6b3fa0"
METAL, GOLD, PLASTIC_W, CHIP = "#c9ced6", "#d4a92f", "#eef0f2", "#2b2f36"


def pcb(part, w, d, col, holes=()):
    part.box(0, 0, 0, w, d, 1.6, col)
    for hx, hy in holes:
        part.circle_top(hx, hy, 1.6, 1.4, GOLD)
        part.circle_top(hx, hy, 1.6, 0.8, "#ffffff")


def header(part, x, y, rows, cols, pitch=2.54, z=1.6, h=2.5, horizontal=True):
    w = cols * pitch if horizontal else rows * pitch
    d = rows * pitch if horizontal else cols * pitch
    part.box(x, y, z, w, d, h, PCB_BLACK, sw=0.6)
    for i in range(cols):
        for j in range(rows):
            px = x + (i + 0.5) * pitch if horizontal else x + (j + 0.5) * pitch
            py = y + (j + 0.5) * pitch if horizontal else y + (i + 0.5) * pitch
            part.rect_top(px - 0.35, py - 0.35, z + h, 0.7, 0.7, GOLD)


def pi5(part):
    pcb(part, 85, 56, PCB_GREEN, [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)])
    header(part, 7.5, 50.3, 2, 20)                                  # 40-pin GPIO
    part.box(27, 20, 1.6, 15, 15, 1.4, METAL)                       # BCM2712
    part.text_top(28.5, 26, 3.0, "BCM2712", 2.0, INK, 700)
    part.box(46, 21, 1.6, 12, 14, 1.1, CHIP)                         # RAM
    part.box(57, 38, 1.6, 9, 9, 1.0, CHIP)                           # RP1
    part.box(42, 41, 1.6, 7, 3.2, 2.0, PLASTIC_W)                    # CSI/DSI
    part.box(50, 41, 1.6, 7, 3.2, 2.0, PLASTIC_W)
    part.box(9, -1.2, 1.6, 9, 7.5, 3.2, METAL)                      # USB-C power
    part.box(24, -1.2, 1.6, 7, 7.5, 3.0, METAL)                     # micro-HDMI x2
    part.box(37, -1.2, 1.6, 7, 7.5, 3.0, METAL)
    part.box(66, 1.5, 1.6, 21.5, 15, 16, METAL)                     # USB 3 stack
    part.box(66, 19.5, 1.6, 21.5, 15, 16, "#5b7fb3")                # USB 2 stack
    part.box(66, 37.5, 1.6, 21.5, 16, 13.5, METAL)                  # Ethernet
    part.text_top(6, 8, 1.6, "Raspberry Pi 5", 4.2, "#e8f5ec", 700)


def cooler(part):
    part.box(0, 0, 0, 56, 40, 2.2, "#a9b4c2")                        # base plate
    for i in range(9):
        part.box(2 + i * 3.6, 2, 2.2, 1.2, 36, 7.5, "#bfc8d4", sw=0.5)
    part.box(36, 3, 2.2, 18, 34, 8, "#1f2329")                       # blower
    part.circle_top(45, 20, 10.2, 7.5, "#3a4049", INK, 0.6)
    part.circle_top(45, 20, 10.2, 2.2, "#7a828d")


def ai_hat(part):
    pcb(part, 65, 56.5, PCB_GREEN, [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)])
    part.box(20, 14, 1.6, 22, 22, 1.8, CHIP)                         # Hailo-8L
    part.text_top(22.5, 22.5, 3.4, "HAILO-8L", 2.6, "#f1f5f9", 700)
    part.box(46, 4, 1.6, 12, 3, 1.5, PLASTIC_W)                      # PCIe FFC
    header(part, 7.5, 50.3, 2, 20, h=1.2)                            # stacking header
    part.text_top(6, 6, 1.6, "AI HAT+  13 TOPS", 3.4, "#e8f5ec", 700)


def standoffs(part):
    for x, y in ((0, 0), (58, 0), (0, 49), (58, 49)):
        part.cylinder(x, y, 0, 2.6, 16, "#c7a24a")
    part.anchor = part.p(58, 0, 8)


def esp32(part):
    pcb(part, 51, 28, PCB_BLACK)
    header(part, 3, -0.6, 1, 15, h=2.0)
    header(part, 3, 26, 1, 15, h=2.0)
    part.box(14, 5, 1.6, 25.5, 18, 3.1, METAL)                       # WROOM module
    part.text_top(18, 9.5, 4.7, "ESP32-WROOM", 2.6, INK, 700)
    part.box(39.5, 5, 1.6, 6, 18, 0.4, "#1b4f2e")                    # antenna
    part.box(-1.5, 10, 1.6, 6, 8, 2.8, METAL)                        # micro-USB
    part.box(8, 3, 1.6, 3, 3, 1.4, "#e5e7eb")                        # EN / BOOT
    part.box(8, 22, 1.6, 3, 3, 1.4, "#e5e7eb")


def tof(part):
    pcb(part, 25, 10.7, PCB_PURPLE, [(2.2, 5.35), (22.8, 5.35)])
    part.box(10.3, 3.5, 1.6, 4.4, 2.4, 1.0, CHIP)                    # VL53L0X
    part.circle_top(11.3, 4.7, 2.6, 0.5, "#9fe0ff")
    part.circle_top(13.7, 4.7, 2.6, 0.5, "#9fe0ff")
    for i in range(6):
        part.circle_top(4.5 + i * 2.54, 9.3, 1.6, 0.55, GOLD)


def camera(part):
    pcb(part, 25, 24, PCB_GREEN, [(2, 2), (23, 2), (2, 22), (23, 22)])
    part.box(5.5, 5, 1.6, 14, 14, 7, PCB_BLACK)                      # M12 holder
    part.cylinder(12.5, 12, 8.6, 6.2, 9, "#30353d")                   # lens barrel
    part.circle_top(12.5, 12, 17.6, 4.2, "#40607a")
    part.circle_top(11.5, 11, 17.6, 1.2, "#b7d4ea")
    part.box(7, 20.5, 1.6, 11, 3, 1.4, PLASTIC_W)                    # ribbon socket


def motor(part):
    pcb(part, 22, 16, PCB_BLUE, [(2, 2), (2, 14)])
    part.cylinder(13, 8, 1.6, 5, 2.8, "#c0c7cf")                      # coin motor
    for i in range(3):
        part.circle_top(4.5, 4.5 + i * 3.2, 1.6, 0.55, GOLD)


def button(part):
    part.box(0, 0, 0, 12, 12, 4.5, "#1f2329")
    part.cylinder(6, 6, 4.5, 4.4, 3.2, "#e11d48")
    for i in range(2):
        part.box(2 + i * 6, 12, -3, 1, 1, 3, METAL, sw=0.4)


def power_bank(part):
    part.box(0, 0, 0, 140, 68, 16, "#3a3f47")
    part.box(-1.2, 26, 4.5, 3, 9, 3.2, "#15181c")                   # USB-C (end face)
    for i in range(4):
        part.circle_top(110 + i * 6, 58, 16, 1.3, "#5eead4")
    part.text_top(14, 20, 16, "10,000 mAh  5V 3A", 7.5, "#cbd5e1", 600)


def housing(part, w=170, d=84, h=34, t=2.4, col="#e2e8f0"):
    """Open tray: outer walls, top rim, inside walls and floor."""
    P = part.p
    # shaft clamp under the tray, drawn first so the tray covers it
    part.cylinder(-6, d / 2 - 9, -10, 9, w + 12, "#cbd5e1", axis="x")
    part.box(t, t, 0, w - 2 * t, d - 2 * t, t, shade(col, -0.05))   # floor
    # inner back walls (visible from inside)
    part.poly([P(t, t, t), P(w - t, t, t), P(w - t, t, h), P(t, t, h)], shade(col, -0.12))
    part.poly([P(t, t, t), P(t, d - t, t), P(t, d - t, h), P(t, t, h)], shade(col, -0.22))
    # outer front walls
    part.poly([P(w, 0, 0), P(w, d, 0), P(w, d, h), P(w, 0, h)], shade(col, -0.18))
    part.poly([P(0, d, 0), P(w, d, 0), P(w, d, h), P(0, d, h)], shade(col, -0.32))
    # rim
    outer = [P(0, 0, h), P(w, 0, h), P(w, d, h), P(0, d, h)]
    inner = [P(t, t, h), P(w - t, t, h), P(w - t, d - t, h), P(t, d - t, h)]
    path = ("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in outer) + " Z M"
            + " L".join(f"{x:.1f},{y:.1f}" for x, y in inner[::-1]) + " Z")
    part.svg.append(f'<path d="{path}" fill="{col}" fill-rule="evenodd" stroke="{INK}" stroke-width="0.9"/>')


def cover(part, w=170, d=84, col="#f1f5f9"):
    part.box(0, 0, 0, w, d, 3, col)
    for i in range(7):                                                # vent slots
        part.rect_top(52 + i * 7, 20, 3, 3.2, 40, "#94a3b8")
    part.rect_top(150, 26, 3, 14, 32, "#1e293b")                     # sensor window
    part.text_top(10, 62, 3, "SMART CANE 2.0", 6.2, "#64748b", 700)


def grip(part):
    part.cylinder(0, 0, 0, 15, 115, "#1f2329")
    for i in range(6):
        part.cylinder(0, 0, 18 + i * 15, 15.4, 2.2, "#2c323a", sw=0.5)


def shaft(part):
    part.cylinder(0, 0, 0, 8, 150, "#f8fafc")
    part.cylinder(0, 0, 0, 8.4, 22, "#dc2626")                        # red band
    part.cylinder(0, 0, -16, 7, 16, "#334155")                        # tip


def earbuds(part):
    for dx in (0, 34):
        part.cylinder(dx, 0, 0, 9, 7, "#334155")
        part.cylinder(dx + 4, 6, 7, 3.4, 9, "#475569")


# ---- the drawing ------------------------------------------------------------

PARTS = [
    # n, name, model / spec, qty, connects to
    (1, "Push button", "12 mm momentary, to GND", 1, "ESP32 D33"),
    (2, "Vibration motor", "Coin ERM motor module", 1, "ESP32 D13 (PWM), 5 V"),
    (3, "Grip", "3D-printed, foam wrap", 1, "Top of the shaft"),
    (4, "Housing cover", "3D-printed, vents + sensor window", 1, "Housing base"),
    (5, "AI HAT+", "Raspberry Pi, Hailo-8L, 13 TOPS", 1, "Pi 5 PCIe + 40-pin"),
    (6, "Standoffs", "M2.5 x 16 mm brass", 4, "Pi 5 to AI HAT+"),
    (7, "Active Cooler", "Raspberry Pi 5 Active Cooler", 1, "Pi 5 SoC, fan header"),
    (8, "Raspberry Pi 5", "2 GB, Raspberry Pi OS Bookworm", 1, "Everything"),
    (9, "ESP32 DevKit V1", "ESP32-WROOM-32, CP2102 USB", 1, "Pi 5 USB"),
    (10, "Power bank", "10,000 mAh, USB-C PD 5 V 3 A min.", 1, "Pi 5 USB-C"),
    (11, "Housing base", "3D-printed tray + shaft clamp", 1, "Cane shaft"),
    (12, "Camera", "Arducam B0310, IMX708, 120° M12", 1, "Pi 5 CAM0 (CSI)"),
    (13, "ToF 1, forward", "VL53L0X breakout, 55° to shaft", 1, "ESP32 I2C0 (D21/D22), D26"),
    (14, "ToF 2, down", "VL53L0X breakout, 15° to shaft", 1, "ESP32 I2C1 (D18/D19), D27"),
    (15, "Cane shaft", "White cane, 124-127 cm (shortened here)", 1, "Clamp of part 11"),
    (16, "Earbuds", "Bluetooth, A2DP speech + mic", 1, "Pi 5 Bluetooth"),
]


def build():
    W, H = 1760, 1740
    k = 2.05
    layout = {}

    def put(n, fn, ox, oy, scale=k):
        part = Part(ox, oy, scale)
        fn(part)
        layout[n] = part

    # Main stack, top to bottom along the assembly axis.
    put(4, cover, 520, 140)
    put(5, ai_hat, 610, 440)
    put(6, standoffs, 614, 630)
    put(7, cooler, 640, 770)
    put(8, pi5, 600, 920)
    put(9, esp32, 900, 1000)
    put(10, power_bank, 520, 1130)
    put(11, housing, 520, 1420)
    put(15, shaft, 1040, 1530, 1.3)
    # Handle group, upper left.
    put(3, grip, 205, 430, 1.6)
    put(1, button, 120, 215)
    put(2, motor, 55, 660)
    # Sensor head group, right.
    put(12, camera, 1110, 330, 3.0)
    put(13, tof, 1150, 560, 3.0)
    put(14, tof, 1150, 740, 3.0)
    put(16, earbuds, 170, 1560, 2.4)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           f'font-family="{FONT}">',
           '<title>Smart cane prototype, exploded view</title>',
           f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
           f'<text x="32" y="48" font-size="28" font-weight="700" fill="{INK}">Exploded view</text>',
           f'<text x="32" y="78" font-size="15" fill="{INK2}">Every part of the cane unit, separated '
           f'along its assembly direction. Boards, chips, ports and headers at their published sizes. '
           f'Housing and power bank representative.</text>']

    # Assembly axes (dashed) between the stacked parts.
    def centre(n):
        x0, y0, x1, y1 = layout[n].bbox()
        return (x0 + x1) / 2, (y0 + y1) / 2
    for a, b in ((4, 5), (5, 6), (6, 7), (7, 8), (8, 10), (10, 11)):
        (ax, ay), (bx, by) = centre(a), centre(b)
        out.append(f'<line x1="{ax:.0f}" y1="{ay:.0f}" x2="{bx:.0f}" y2="{by:.0f}" stroke="{LINE}" '
                   f'stroke-width="1.2" stroke-dasharray="7 6"/>')
    for a, b in ((12, 4), (13, 4), (14, 4), (9, 8), (1, 3), (2, 3), (11, 15)):
        (ax, ay), (bx, by) = centre(a), centre(b)
        out.append(f'<path d="M{ax:.0f},{ay:.0f} C{(ax + bx) / 2:.0f},{ay:.0f} {(ax + bx) / 2:.0f},'
                   f'{by:.0f} {bx:.0f},{by:.0f}" fill="none" stroke="{LINE}" stroke-width="1.1" '
                   f'stroke-dasharray="3 5"/>')

    order = [15, 11, 10, 9, 8, 7, 6, 5, 4, 3, 1, 2, 12, 13, 14, 16]
    for n in order:
        out.extend(layout[n].svg)

    # Group labels.
    for x, y, t in ((60, 175, "HANDLE"), (1020, 245, "SENSOR HEAD, FRONT OF THE HOUSING"),
                    (520, 120, "ELECTRONICS HOUSING"), (110, 1500, "WORN BY THE USER")):
        out.append(f'<text x="{x}" y="{y}" font-size="12.5" font-weight="700" letter-spacing="1.6" '
                   f'fill="{MUTED}">{t}</text>')

    # Balloons: placed at the part's right edge, leader to the part's middle.
    for n, *_ in PARTS:
        x0, y0, x1, y1 = layout[n].bbox()
        cx, cy = layout[n].anchor or ((x0 + x1) / 2, (y0 + y1) / 2)
        bx, by = x1 + 26, y0 + 10
        if n in (1, 2, 3, 16):
            bx = x0 - 24 if n != 3 else x1 + 24
        bx = max(22, min(bx, 1295))
        out.append(f'<line x1="{cx:.0f}" y1="{cy:.0f}" x2="{bx:.0f}" y2="{by:.0f}" stroke="{INK2}" '
                   f'stroke-width="1"/><circle cx="{cx:.0f}" cy="{cy:.0f}" r="2.6" fill="{INK2}"/>')
        out.append(f'<circle cx="{bx:.0f}" cy="{by:.0f}" r="15" fill="#ffffff" stroke="{INK}" '
                   f'stroke-width="1.6"/><text x="{bx:.0f}" y="{by + 5:.0f}" text-anchor="middle" '
                   f'font-size="14" font-weight="700" fill="{INK}">{n}</text>')

    # Parts list.
    tx, ty, rh = 1335, 120, 74
    out.append(f'<rect x="{tx - 18}" y="{ty - 40}" width="{W - tx - 4}" height="{len(PARTS) * rh + 58}" '
               f'rx="10" fill="#f8fafc" stroke="#e2e8f0"/>')
    out.append(f'<text x="{tx}" y="{ty - 12}" font-size="13" font-weight="700" letter-spacing="1.4" '
               f'fill="{MUTED}">PARTS LIST</text>')
    for i, (n, name, spec, qty, conn) in enumerate(PARTS):
        y = ty + 20 + i * rh
        out.append(f'<circle cx="{tx + 12}" cy="{y - 5}" r="12" fill="#ffffff" stroke="{INK}" stroke-width="1.4"/>'
                   f'<text x="{tx + 12}" y="{y}" text-anchor="middle" font-size="12" font-weight="700" '
                   f'fill="{INK}">{n}</text>')
        out.append(f'<text x="{tx + 34}" y="{y}" font-size="15" font-weight="700" fill="{INK}">{name}'
                   f'{f"  x{qty}" if qty > 1 else ""}</text>')
        out.append(f'<text x="{tx + 34}" y="{y + 20}" font-size="12.5" fill="{INK2}">{spec}</text>')
        out.append(f'<text x="{tx + 34}" y="{y + 38}" font-size="12.5" fill="{MUTED}">to: {conn}</text>')
    out.append(f'<text x="32" y="{H - 24}" font-size="12.5" fill="{MUTED}">Cables (not drawn): CSI '
               f'ribbon camera to CAM0, PCIe ribbon HAT to Pi, USB ESP32 to Pi, USB-C power bank to Pi, '
               f'Dupont leads ESP32 to sensors, motor and button. Wiring table: docs/hardware.md.</text>')
    out.append("</svg>")
    return "\n".join(out)


def main():
    path = os.path.join(HERE, "exploded_view.svg")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(build() + "\n")
    print("wrote", path)


if __name__ == "__main__":
    main()
