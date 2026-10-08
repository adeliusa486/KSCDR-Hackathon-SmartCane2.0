#!/usr/bin/env python3
"""Draw the exploded view and the cross-section of the smart cane prototype.

    python docs/figures/make_figures.py      # writes exploded_view.svg, cross_section.svg
    (the exploded view itself is drawn by exploded.py)

Schematic figures. Board outlines use the manufacturers' sizes (Raspberry Pi 5
85 x 56 mm, AI HAT+ 65 x 56.5 mm, ESP32 DevKit V1 about 51 x 28 mm). The
3D-printed housing has no published CAD file, so its shape and the power
bank's size (models differ) are representative. Mount positions and angles
are the ones recorded in docs/hardware.md.
"""
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = 'font-family="Segoe UI, Helvetica, Arial, sans-serif"'
INK, MUTED, LINE = "#111827", "#4b5563", "#6b7280"
C30, S30 = math.cos(math.radians(30)), math.sin(math.radians(30))


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, t, size=14, weight=400, fill=INK, anchor="start", extra=""):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}" {extra}>{esc(t)}</text>')


# ---------------------------------------------------------------- cross-section

def cross_section():
    W, H = 1240, 860
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" {FONT}>',
         '<title>Smart cane prototype, cross-section along the shaft</title>',
         '<defs><pattern id="hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
         '<line x1="0" y1="0" x2="0" y2="8" stroke="#9ca3af" stroke-width="2"/></pattern>'
         '<marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
         '<path d="M0,0 L10,5 L0,10 z" fill="#374151"/></marker></defs>',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
         text(30, 40, "Cross-section A-A through the housing, along the shaft", 22, 700),
         text(30, 64, "Shaft drawn horizontal, tip to the right. The top of the drawing faces forward when "
                      "walking. Schematic, 2.4 px per mm.", 14, fill=MUTED)]

    def rect(x, y, w, h, fill, rx=0, sw=1.6):
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" '
                 f'stroke="#111827" stroke-width="{sw}"/>')

    def wire(points, colour):
        o.append('<polyline points="' + " ".join(f"{x},{y}" for x, y in points)
                 + f'" fill="none" stroke="{colour}" stroke-width="2.4" stroke-linejoin="round"/>')

    # shaft and grip
    rect(40, 560, 1160, 38, "#1f2937", sw=0)
    rect(1150, 560, 50, 38, "#dc2626", sw=0)
    o.append(text(1195, 620, "toward the tip", 13, fill=MUTED, anchor="end"))
    o.append(text(45, 620, "toward the grip end", 13, fill=MUTED))
    rect(60, 478, 288, 82, "url(#hatch)", rx=20, sw=2)
    rect(118, 464, 34, 14, "#111827", rx=4)                 # the button
    o.append('<circle cx="250" cy="519" r="20" fill="#a78bfa" stroke="#111827" stroke-width="2"/>')

    # housing shell with vent slots over the fan
    o.append('<path d="M360 560 L360 360 Q360 330 390 330 L900 330 L1000 450 L1000 560 Z" '
             'fill="url(#hatch)" fill-opacity="0.45" stroke="#111827" stroke-width="2.5"/>')
    o.append('<path d="M368 552 L368 362 Q368 338 392 338 L896 338 L992 453 L992 552 Z" fill="#ffffff"/>')
    for vx in range(436, 556, 18):
        rect(vx, 330, 10, 8, "#ffffff", sw=0)

    # power bank, Pi stack, ESP32
    rect(380, 513, 336, 38, "#fde68a", rx=6, sw=2)
    rect(390, 486, 204, 5, "#22c55e")                    # Pi 5
    rect(420, 462, 144, 24, "#94a3b8")                   # Active Cooler
    rect(396, 448, 7, 38, "#d1d5db", sw=1)               # spacers
    rect(581, 448, 7, 38, "#d1d5db", sw=1)
    rect(390, 443, 156, 5, "#4ade80")                    # AI HAT+
    rect(456, 431, 40, 12, "#111827", sw=0)              # Hailo module
    rect(620, 486, 122, 5, "#60a5fa")                    # ESP32
    rect(612, 482, 14, 12, "#9ca3af", sw=1)              # its USB socket

    # sensor head: camera + ToF 1 at 55 deg from the shaft, ToF 2 at 15 deg
    o.append('<g transform="rotate(-55 925 455)">'
             '<rect x="895" y="425" width="60" height="60" fill="#fca5a5" stroke="#111827" stroke-width="2"/>'
             '<circle cx="955" cy="440" r="12" fill="#111827"/>'
             '<rect x="953" y="460" width="10" height="16" fill="#f59e0b" stroke="#111827"/></g>')
    o.append('<g transform="rotate(-15 955 528)">'
             '<rect x="933" y="518" width="44" height="20" fill="#f87171" stroke="#111827" stroke-width="2"/></g>')

    def ray(x, y, ang, length, colour, label, lx, ly):
        ex = x + length * math.cos(math.radians(ang))
        ey = y + length * math.sin(math.radians(ang))
        o.append(f'<line x1="{x}" y1="{y}" x2="{ex:.0f}" y2="{ey:.0f}" stroke="{colour}" stroke-width="2.5" '
                 f'stroke-dasharray="7 5" marker-end="url(#a)"/>')
        o.append(text(lx, ly, label, 14, 700, colour))

    ray(968, 410, -55, 170, "#d97706", "camera + ToF 1: 55° from the shaft", 940, 250)
    ray(985, 520, -15, 200, "#dc2626", "ToF 2: 15° from the shaft", 1010, 452)

    # cables, routed in straight runs
    wire([(905, 482), (905, 505), (600, 505), (594, 491)], "#db2777")              # CSI
    wire([(612, 488), (600, 488)], "#2563eb")                                     # USB ESP32 -> Pi
    wire([(380, 532), (372, 532), (372, 489), (390, 489)], "#ca8a04")             # USB-C bank -> Pi
    wire([(742, 486), (820, 486), (895, 455)], "#0891b2")                         # I2C ToF 1
    wire([(742, 491), (820, 491), (820, 528), (935, 528)], "#0891b2")             # I2C ToF 2
    wire([(660, 486), (660, 350), (376, 350), (376, 519), (270, 519)], "#9333ea")    # motor
    wire([(668, 486), (668, 356), (382, 356), (382, 470), (152, 470)], "#9333ea")    # button

    # numbered balloons: (number, point on the part, balloon centre or None = on the part)
    balloons = [(1, (139, 464), (139, 418)), (2, (250, 499), (250, 438)),
                (3, (476, 431), (440, 392)), (4, (500, 462), (520, 392)),
                (5, (560, 486), (600, 392)), (6, (700, 486), (720, 420)),
                (7, (548, 532), None), (8, (900, 430), (840, 392)),
                (9, (955, 528), (900, 600)), (10, (960, 405), (1040, 360)),
                (11, (300, 579), None)]
    for n, (px, py), b in balloons:
        if b is None:
            bx, by = px, py
        else:
            bx, by = b
            o.append(f'<line x1="{px}" y1="{py}" x2="{bx}" y2="{by}" stroke="{LINE}" stroke-width="1.2"/>')
            o.append(f'<circle cx="{px}" cy="{py}" r="3" fill="{LINE}"/>')
        o.append(f'<circle cx="{bx}" cy="{by}" r="14" fill="#ffffff" stroke="#111827" stroke-width="1.8"/>')
        o.append(text(bx, by + 5, str(n), 14, 700, anchor="middle"))

    parts = ["1  Button: AI assistant, press / hold (GPIO33)",
             "2  Vibration motor against the grip wall (GPIO13)",
             "3  AI HAT+ with the Hailo-8L, on spacers",
             "4  Active Cooler, fan under the vent slots",
             "5  Raspberry Pi 5, 85 x 56 mm",
             "6  ESP32 DevKit V1, safety controller",
             "7  Power bank 10,000 mAh on the shaft clamp",
             "8  Camera (IMX708, 120° M12 lens) + ToF 1, forward",
             "9  ToF 2, down, 110 cm from the tip",
             "10 Housing shell, 3D-printed",
             "11 Cane shaft"]
    for i, t in enumerate(parts):
        o.append(text(60 + (i // 6) * 560, 672 + (i % 6) * 22, t, 14, fill=INK))
    legend = [("#db2777", "CSI ribbon: camera to CAM0"),
              ("#2563eb", "USB: ESP32 to Pi (power, serial, flashing)"),
              ("#ca8a04", "USB-C: power bank to Pi"),
              ("#0891b2", "I2C + XSHUT: ESP32 to each ToF, one bus each"),
              ("#9333ea", "Motor and button wires to the grip")]
    for i, (c, t) in enumerate(legend):
        yy = 818 + (i // 3) * 24
        xx = 60 + (i % 3) * 390
        o.append(f'<line x1="{xx}" y1="{yy - 5}" x2="{xx + 28}" y2="{yy - 5}" stroke="{c}" stroke-width="3"/>')
        o.append(text(xx + 36, yy, t, 13, fill=MUTED))
    o.append("</svg>")
    return "\n".join(o), (W, H)


def main():
    import exploded
    for name, fn in (("exploded_view.svg", lambda: (exploded.build(), None)),
                     ("cross_section.svg", cross_section)):
        svg, _ = fn()
        with open(os.path.join(HERE, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(svg + "\n")
        print("wrote", name)


if __name__ == "__main__":
    main()
