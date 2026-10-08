#!/usr/bin/env python3
"""Write docs/objects.md: every class the cane knows, grouped, with training
counts, validation accuracy and what the cane does with it.

    python docs/make_objects.py

Reads models/smartcane152_v3/smartcane152.txt, data/merged_v2/class_counts.csv,
docs/results/v3_per_class.csv, and the urgency list and height table from
code/speak_detect.py and code/detect.py, so the page follows the code.
"""
import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "code"))
import detect          # noqa: E402
import speak_detect    # noqa: E402

GROUPS = [
    ("People and mobility", ["person", "child", "cyclist", "motorcyclist", "wheelchair", "stroller"]),
    ("Animals", ["dog", "cat", "bird", "horse", "cow", "sheep", "goat", "camel"]),
    ("Vehicles", ["car", "bus", "truck", "van", "taxi", "ambulance", "motorcycle", "bicycle",
                  "e-scooter", "skateboard", "train", "golf cart", "shopping cart", "trailer"]),
    ("Ground hazards and level changes", ["open hole", "pothole", "manhole", "storm drain", "stairs",
                                          "escalator", "curb", "curb ramp", "ramp", "speed bump",
                                          "sidewalk crack", "rail track", "tactile paving",
                                          "swimming pool"]),
    ("Crossings, signals and signs", ["crosswalk", "traffic light", "pedestrian signal", "crosswalk button",
                                      "stop sign", "traffic sign", "yield sign", "do not enter sign",
                                      "one way sign", "pedestrian crossing sign", "speed limit sign",
                                      "construction sign", "sidewalk closed sign", "bus stop sign",
                                      "exit sign", "wet floor sign"]),
    ("Street furniture and obstacles", ["pole", "utility pole", "street light", "bollard", "traffic cone",
                                        "barrier", "fence", "barrel", "fire hydrant", "parking meter",
                                        "bench", "trash can", "bike rack", "mailbox", "utility box",
                                        "billboard", "sidewalk sign", "kiosk", "fountain", "sculpture",
                                        "pillar", "ladder", "tent", "potted plant"]),
    ("Buildings and entrances", ["door", "door handle", "window", "building", "elevator", "atm"]),
    ("Trees and plants", ["tree", "palm tree", "plant"]),
    ("Furniture", ["chair", "stool", "couch", "bed", "table", "desk", "coffee table", "nightstand",
                   "chest of drawers", "wardrobe", "cabinet", "shelf", "bookcase", "countertop",
                   "mirror", "curtain", "lamp", "ceiling fan", "pillow", "clock"]),
    ("Bathroom and kitchen", ["toilet", "sink", "bathtub", "shower", "refrigerator", "microwave", "oven",
                              "stove", "washing machine", "kettle", "towel", "toothbrush"]),
    ("Electronics", ["tv", "laptop", "keyboard", "mouse", "remote", "cell phone"]),
    ("Things you carry or find", ["backpack", "handbag", "suitcase", "umbrella", "glasses", "book",
                                  "bottle", "cup", "can", "box", "plastic bag", "tire", "ball", "toy",
                                  "scissors", "knife", "fork", "spoon", "bowl", "plate",
                                  "banana", "apple", "orange"]),
]


def num(v, fmt="{:.2f}"):
    return fmt.format(float(v)) if v not in ("", None) else "-"


def main():
    names = [l.strip() for l in open(os.path.join(ROOT, "models/smartcane152_v3/smartcane152.txt")) if l.strip()]
    grouped = [c for _, cs in GROUPS for c in cs]
    missing = sorted(set(names) - set(grouped))
    extra = sorted(set(grouped) - set(names))
    if missing or extra or len(grouped) != len(set(grouped)):
        sys.exit(f"groups do not match the model: missing {missing}, extra {extra}")

    counts = {r["class"]: r for r in csv.DictReader(open(os.path.join(ROOT, "data/merged_v2/class_counts.csv")))}
    val = {r["class"]: r for r in csv.DictReader(open(os.path.join(ROOT, "docs/results/v3_per_class.csv")))}
    urgent = {c: i + 1 for i, c in enumerate(speak_detect.PRIORITY)}

    out = ["# Objects the cane knows", "",
           f"The detector names **{len(names)} kinds of object**. Each one is spoken as "
           "\"name, direction, distance\", for example \"chair ahead, 1.3 meters\" or "
           "\"car left, about 4 meters\". Anything the model is not sure of (confidence "
           "under 0.35), or anything it was never trained on, is announced as \"obstacle\" "
           "with its direction and distance, so nothing physical is silently dropped.", "",
           "How to read the tables:", "",
           "- **Urgency**: rank in the speech order (1 = said first). Drop-offs come first, "
           "then vehicles, then people and animals, then street obstacles. Unranked objects "
           "follow, nearest first.",
           "- **Train boxes**: labelled examples in the training set (human labels plus "
           "checked pseudo-labels).",
           "- **mAP50 / recall**: accuracy of smartcane152_v3 on 27,906 validation images. "
           "Recall is the share of real objects found. Above 0.7 mAP50 is reliable, 0.5 to "
           "0.7 usable, under 0.5 often heard as \"obstacle\" instead of its name.",
           "- **Camera distance**: yes = the camera estimates the distance in metres from the "
           "object's typical height. Straight ahead, the forward ToF sensor measures it instead.",
           ""]
    total_boxes = 0
    for title, classes in GROUPS:
        out += [f"## {title}", "",
                "| Object | Urgency | Train boxes | mAP50 | Recall | Camera distance |",
                "|---|---|---|---|---|---|"]
        for c in classes:
            k = counts.get(c, {})
            v = val.get(c, {})
            tb = int(k.get("train_boxes", 0) or 0)
            total_boxes += tb
            out.append(f"| {c} | {urgent.get(c, '')} | {tb:,} | {num(v.get('mAP50'))} | "
                       f"{num(v.get('recall'))} | "
                       f"{'yes' if c in detect.TYPICAL_HEIGHT_M else ''} |")
        out.append("")
    out += ["## Totals", "",
            f"{len(names)} classes, {total_boxes:,} labelled boxes in the training split. "
            "Validation: mAP50 0.535, mAP50-95 0.376 over all classes.", "",
            "Generated by `docs/make_objects.py` from the model's label file, "
            "`data/merged_v2/class_counts.csv` and `docs/results/v3_per_class.csv`.", ""]
    with open(os.path.join(ROOT, "docs/objects.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out))
    print(f"wrote docs/objects.md: {len(names)} classes, {total_boxes} train boxes")
    update_readme(val)


def update_readme(val):
    """Refresh the object list between the OBJECTS markers in README.md."""
    path = os.path.join(ROOT, "README.md")
    if not os.path.exists(path):
        return
    text = open(path, encoding="utf-8").read()
    start, end = "<!-- OBJECTS:START -->", "<!-- OBJECTS:END -->"
    if start not in text or end not in text:
        return
    rows = ["| Group | Objects |", "|---|---|"]
    for title, classes in GROUPS:
        names = ", ".join(f"**{c}**" if float(val.get(c, {}).get("mAP50") or 0) >= 0.7 else c
                          for c in classes)
        rows.append(f"| {title} ({len(classes)}) | {names} |")
    block = (start + "\n\n" + "\n".join(rows) + "\n\n**Bold**: reliable, mAP50 of 0.70 or more on "
             "the validation set. Accuracy, training examples and speech urgency for every object: "
             "[docs/objects.md](docs/objects.md).\n\n" + end)
    text = text[:text.index(start)] + block + text[text.index(end) + len(end):]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("updated the object list in README.md")


if __name__ == "__main__":
    main()
