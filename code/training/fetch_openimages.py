#!/usr/bin/env python3
"""Smart cane - pull a city-focused subset of Open Images V7 and write YOLO labels.

Why this exists
---------------
Open Images V7 has 601 classes and is freely downloadable with no account, no
API key and no licence gate. That makes it the only large source we can use
without waiting on anyone. The full set is roughly 560 GB, which is absurd for
our purpose, so this script pulls only the classes a blind pedestrian in a city
actually needs, and caps how many images come down per class.

What it is NOT
--------------
Open Images has no pothole, no open drain, no kerb and no bollard. Those come
from the specialist datasets in classes.yaml and have to be merged in later.
This script builds the broad city foundation, not the hazard layer.

    python fetch_openimages.py --out C:/ml/smartcane/data --per-class 400
    python fetch_openimages.py --out ... --list        # just show the classes
"""
import argparse
import sys
from pathlib import Path

# Curated from the full 601. Every entry is something a person walking through
# a city can collide with, trip over, needs to find, or needs to be warned
# about. Kitchen utensils, musical instruments and 200 food items are excluded
# on purpose: they cost accuracy on the classes that matter and speak_detect.py
# reports anything unrecognised as "obstacle" anyway.
CITY_CLASSES = [
    # --- people -----------------------------------------------------------
    "Person", "Man", "Woman", "Boy", "Girl",
    # --- things that move and can hit you --------------------------------
    "Car", "Bus", "Truck", "Van", "Taxi", "Ambulance", "Limousine",
    "Motorcycle", "Bicycle", "Train", "Cart", "Golf cart", "Segway",
    "Wheelchair", "Snowplow", "Boat",
    # --- street infrastructure -------------------------------------------
    "Traffic light", "Traffic sign", "Stop sign", "Street light",
    "Fire hydrant", "Parking meter", "Bench", "Waste container", "Billboard",
    "Poster", "Flag", "Fountain", "Tower", "Lighthouse", "Barrel",
    "Vehicle registration plate",
    # --- buildings and the ways into them ---------------------------------
    "Building", "Office building", "House", "Skyscraper", "Convenience store",
    "Castle", "Porch", "Door", "Door handle", "Window", "Stairs", "Ladder",
    "Tent",
    # --- planting, which blocks footpaths everywhere in India -------------
    "Tree", "Palm tree", "Plant", "Flowerpot", "Houseplant",
    # --- animals on the street --------------------------------------------
    "Dog", "Cat", "Cattle", "Horse", "Goat", "Sheep", "Chicken", "Bird",
    "Monkey", "Pig", "Mule",
    # --- loose objects underfoot or carried -------------------------------
    "Backpack", "Handbag", "Suitcase", "Luggage and bags", "Umbrella", "Box",
    "Plastic bag", "Tire", "Wheel", "Bottle", "Tin can",
    # --- indoor landmarks, for navigation inside buildings ----------------
    "Chair", "Table", "Couch", "Bed", "Toilet", "Sink", "Television",
    "Laptop", "Mobile phone", "Clock", "Bookcase", "Shelf", "Mirror",
    "Curtain", "Stool", "Desk",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-class", type=int, default=400,
                    help="max images per class. 400 x ~95 classes is roughly "
                         "25-35k images and 10-20 GB.")
    ap.add_argument("--splits", default="train,validation")
    ap.add_argument("--list", action="store_true",
                    help="print the class list and exit, download nothing")
    args = ap.parse_args()

    if args.list:
        print(f"{len(CITY_CLASSES)} city classes selected from Open Images V7:\n")
        for i in range(0, len(CITY_CLASSES), 6):
            print("  " + ", ".join(CITY_CLASSES[i:i + 6]))
        return

    try:
        import fiftyone as fo
        import fiftyone.zoo as foz
    except ImportError:
        sys.exit("pip install fiftyone")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    for split in args.splits.split(","):
        split = split.strip()
        print(f"\n=== downloading Open Images V7 '{split}' ===")
        print(f"    {len(CITY_CLASSES)} classes, up to {args.per_class} images each")
        ds = foz.load_zoo_dataset(
            "open-images-v7",
            split=split,
            label_types=["detections"],
            classes=CITY_CLASSES,
            max_samples=args.per_class * len(CITY_CLASSES),
            seed=51,
            shuffle=True,
            dataset_name=f"oiv7_city_{split}",
        )
        print(f"    {len(ds)} images")

        yolo_split = "val" if split.startswith("val") else "train"
        export_dir = out / "openimages"
        print(f"    exporting YOLO labels to {export_dir}/{yolo_split}")
        ds.export(
            export_dir=str(export_dir),
            dataset_type=fo.types.YOLOv5Dataset,
            label_field="ground_truth",
            split=yolo_split,
            classes=CITY_CLASSES,
        )

    print("\ndone. next: merge with the hazard datasets, then train.py")


if __name__ == "__main__":
    main()
