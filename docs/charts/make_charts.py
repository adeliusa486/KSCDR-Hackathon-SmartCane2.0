#!/usr/bin/env python3
"""Draw the README / website charts from the repository's own data files.

    python docs/charts/make_charts.py      # writes <name>-light.svg and <name>-dark.svg

Every chart comes in a light and a dark version so it reads in either GitHub
theme (README uses <picture> with prefers-color-scheme). Text is converted
to paths, so the SVGs look the same everywhere. Colours: the two-slot
categorical palette (blue, orange) validated for colour-blind separation and
contrast in both modes with the dataviz validator (8 Oct 2026, all pass).

Data sources:
  camera_path   docs/results.md, A/B run on the cane's Hailo, 8 Oct 2026
  safety        docs/results/v3_per_class.csv (val_per_class.py)
  training      docs/results/v3_training/results.csv and v2_results.csv
  dataset       data/merged_v2/source_counts.csv
"""
import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

THEMES = {
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e", muted="#898781",
                  grid="#e1e0d9", axis="#c3c2b7", s1="#2a78d6", s2="#eb6834"),
    "dark": dict(surface="#1a1a19", ink="#ffffff", ink2="#c3c2b7", muted="#898781",
                 grid="#2c2c2a", axis="#383835", s1="#3987e5", s2="#d95926"),
}
plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
    "svg.fonttype": "path",
    "font.size": 11,
})


def frame(t, w=9.0, h=4.6, title="", subtitle=""):
    fig, ax = plt.subplots(figsize=(w, h), dpi=100)
    fig.patch.set_facecolor(t["surface"])
    ax.set_facecolor(t["surface"])
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(t["axis"])
    ax.tick_params(colors=t["muted"], length=0, labelsize=10)
    for lbl in ax.get_yticklabels():
        lbl.set_color(t["ink2"])
    # Positions in inches from the top, so short and tall charts match.
    fig.text(0.012, 1 - 0.14 / h, title, ha="left", va="top", fontsize=15, weight="bold", color=t["ink"])
    if subtitle:
        fig.text(0.012, 1 - 0.46 / h, subtitle, ha="left", va="top", fontsize=10.5, color=t["ink2"])
    return fig, ax


def save(fig, name, mode):
    path = os.path.join(HERE, f"{name}-{mode}.svg")
    fig.savefig(path, facecolor=fig.get_facecolor(), metadata={"Date": None})
    plt.close(fig)
    # Matplotlib writes an XML DOCTYPE. Nothing needs it, and some web hosts
    # and SVG sanitisers refuse files that carry DTD declarations.
    import re
    with open(path, encoding="utf-8") as fh:
        svg = fh.read()
    svg = re.sub(r'<!DOCTYPE[^>]*>\s*', "", svg, count=1)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(svg)
    return path


def camera_path(t, mode):
    rows = [  # label, named %, noticed %
        ("Old camera path\n(squeezed 1.78x, red and blue swapped)", 40, 53),
        ("Colours fixed, still squeezed", 49, 62),
        ("Letterboxed, colours still swapped", 47, 59),
        ("New camera path\n(letterboxed, correct colours)", 55, 66),
        ("New path, camera turned 90°", 6, 13),
    ]
    fig, ax = frame(t, 9.0, 4.9, "What the camera path costs the model",
                    "408 labelled street photos cropped to 16:9, run on the cane's own Hailo-8L "
                    "(2,943 objects)")
    n = len(rows)
    ys = list(range(n))[::-1]
    h = 0.36
    for y, (label, named, noticed) in zip(ys, rows):
        ax.barh(y + h / 2, named, height=h, color=t["s1"], edgecolor=t["surface"], linewidth=2)
        ax.barh(y - h / 2, noticed, height=h, color=t["s2"], edgecolor=t["surface"], linewidth=2)
        ax.text(named + 1, y + h / 2, f"{named} %", va="center", fontsize=10, color=t["ink"])
        ax.text(noticed + 1, y - h / 2, f"{noticed} %", va="center", fontsize=10, color=t["ink2"])
    ax.set_yticks(ys)
    ax.set_yticklabels([r[0] for r in rows], color=t["ink2"], fontsize=10)
    ax.get_yticklabels()[3].set_color(t["ink"])
    ax.get_yticklabels()[3].set_fontweight("bold")
    ax.set_xlim(0, 80)
    ax.set_xticks([0, 20, 40, 60, 80])
    ax.set_xticklabels([f"{v} %" for v in (0, 20, 40, 60, 80)])
    ax.xaxis.grid(True, color=t["grid"], linewidth=1)
    ax.set_axisbelow(True)
    leg = ax.legend(["Named correctly", "Noticed (named or \"obstacle\")"], loc="lower right",
                    frameon=False, fontsize=10, labelcolor=t["ink2"], ncol=2,
                    bbox_to_anchor=(1.0, 1.0))
    for hnd, c in zip(leg.legend_handles, (t["s1"], t["s2"])):
        hnd.set_color(c)
    fig.subplots_adjust(left=0.33, right=0.97, top=0.80, bottom=0.08)
    return save(fig, "camera-path", mode)


def safety(t, mode):
    want = ["person", "car", "dog", "open hole", "laptop", "chair", "stairs", "motorcycle",
            "traffic light", "table", "pothole", "bollard", "door", "desk", "pole", "curb",
            "manhole", "cabinet", "crosswalk"]
    rows = {r["class"]: r for r in csv.DictReader(open(os.path.join(ROOT, "docs/results/v3_per_class.csv")))}
    data = sorted(((c, float(rows[c]["mAP50"])) for c in want), key=lambda kv: kv[1])
    fig, ax = frame(t, 9.0, 6.4, "How well each object is detected",
                    "smartcane152_v3, mAP50 on 27,906 validation images. Weak classes are "
                    "still announced as \"obstacle\" when seen")
    ys = range(len(data))
    ax.barh(list(ys), [v for _, v in data], height=0.62, color=t["s1"],
            edgecolor=t["surface"], linewidth=2)
    for y, (c, v) in zip(ys, data):
        ax.text(v + 0.01, y, f"{v:.2f}", va="center", fontsize=9.5, color=t["ink"],
                bbox=dict(facecolor=t["surface"], edgecolor="none", pad=1.2), zorder=3)
    ax.set_yticks(list(ys))
    ax.set_yticklabels([c for c, _ in data], fontsize=10, color=t["ink2"])
    ax.axvline(0.535, color=t["muted"], linestyle=(0, (4, 3)), linewidth=1.2)
    ax.text(0.54, len(data) - 0.4, "all 152 classes: 0.535", fontsize=9.5, color=t["ink2"], va="bottom")
    ax.set_xlim(0, 1.0)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.xaxis.grid(True, color=t["grid"], linewidth=1)
    ax.set_axisbelow(True)
    fig.subplots_adjust(left=0.16, right=0.97, top=0.86, bottom=0.06)
    return save(fig, "safety-classes", mode)


def training(t, mode):
    def load(p):
        out = []
        for r in csv.DictReader(open(os.path.join(ROOT, p))):
            r = {k.strip(): v for k, v in r.items()}
            out.append((int(r["epoch"]), float(r["metrics/mAP50(B)"])))
        return out
    v3 = load("docs/results/v3_training/results.csv")
    v2 = load("docs/results/v3_training/v2_results.csv")
    fig, ax = frame(t, 9.0, 4.6, "Training the 152-class model",
                    "mAP50 on 27,906 validation images after each epoch, YOLO11s on one "
                    "RTX 4060 laptop")
    ax.plot([e for e, _ in v2], [m for _, m in v2], color=t["s2"], linewidth=2, marker="o",
            markersize=5, markeredgecolor=t["surface"], markeredgewidth=2)
    ax.plot([e for e, _ in v3], [m for _, m in v3], color=t["s1"], linewidth=2)
    be, bm = max(v3, key=lambda x: x[1])
    ax.plot([be], [bm], "o", color=t["s1"], markersize=8, markeredgecolor=t["surface"], markeredgewidth=2)
    ax.annotate(f"best: epoch {be}, {bm:.3f}", (be, bm), xytext=(be - 9.5, bm + 0.06),
                fontsize=10, color=t["ink"], arrowprops=dict(arrowstyle="-", color=t["muted"], lw=1))
    ax.text(v2[-1][0] + 0.5, v2[-1][1], "v2, learning rate 0.01:\nfell when warm-up ended",
            fontsize=10, color=t["ink2"], va="center")
    ax.text(v3[-1][0] - 0.2, v3[-1][1] - 0.045, "v3 fine-tune from v2,\nlearning rate 0.002", fontsize=10,
            color=t["ink2"], ha="right", va="top")
    ax.set_xlim(0.5, 28)
    ax.set_ylim(0.15, 0.65)
    ax.set_xticks([1, 5, 10, 15, 20, 25])
    ax.set_xlabel("epoch", color=t["muted"], fontsize=10)
    ax.yaxis.grid(True, color=t["grid"], linewidth=1)
    ax.set_axisbelow(True)
    leg = ax.legend(["v2", "v3"], loc="lower right", frameon=False, fontsize=10, labelcolor=t["ink2"],
                    ncol=2, bbox_to_anchor=(1.0, 1.0))
    for hnd, c in zip(leg.legend_handles, (t["s2"], t["s1"])):
        hnd.set_color(c)
    fig.subplots_adjust(left=0.07, right=0.97, top=0.80, bottom=0.13)
    return save(fig, "training", mode)


def dataset(t, mode):
    groups = {"Open Images V7": 0, "Roboflow (20 projects)": 0, "COCO 2017": 0,
              "Mapillary Traffic Signs": 0, "Mapillary Vistas": 0}
    for r in csv.DictReader(open(os.path.join(ROOT, "data/merged_v2/source_counts.csv"))):
        s, n = r["source"], int(r["images"])
        key = ("Open Images V7" if s.startswith("oiv7") else "Roboflow (20 projects)" if s.startswith("rf_")
               else "COCO 2017" if s == "coco" else "Mapillary Traffic Signs" if s == "mtsd"
               else "Mapillary Vistas" if s == "vistas" else None)
        if key:
            groups[key] += n
    data = sorted(groups.items(), key=lambda kv: kv[1])
    total = sum(groups.values())
    fig, ax = frame(t, 9.0, 3.6, "Where the training images come from",
                    f"{total:,} images, 2,168,416 labelled boxes in the training split")
    ys = range(len(data))
    ax.barh(list(ys), [v for _, v in data], height=0.6, color=t["s1"], edgecolor=t["surface"], linewidth=2)
    for y, (k, v) in zip(ys, data):
        ax.text(v + total * 0.006, y, f"{v:,}  ({100 * v / total:.0f} %)", va="center", fontsize=10, color=t["ink"])
    ax.set_yticks(list(ys))
    ax.set_yticklabels([k for k, _ in data], fontsize=10, color=t["ink2"])
    ax.set_xlim(0, max(groups.values()) * 1.28)
    ax.set_xticks([])
    ax.spines["bottom"].set_visible(False)
    fig.subplots_adjust(left=0.22, right=0.97, top=0.72, bottom=0.04)
    return save(fig, "dataset", mode)


def main():
    for mode, t in THEMES.items():
        for fn in (camera_path, safety, training, dataset):
            print("wrote", os.path.relpath(fn(t, mode), ROOT))


if __name__ == "__main__":
    main()
