#!/usr/bin/env python3
"""Smart cane - train the custom detector, then export it for the Hailo-8L.

Runs on the development laptop (RTX 4060 Laptop, 8 GB VRAM), not on the Pi.

    python train.py --data C:/ml/smartcane/data/smartcane.yaml
    python train.py --data ... --export        # ONNX only, no training

WHY yolov8s AND NOT SOMETHING BIGGER
------------------------------------
Measured on our actual board, not guessed:

    yolov8s   ~44 mAP   58.1 FPS      <- chosen
    yolov7     50.6     36.7
    yolov8x    53.5     16.2
    yolov11x   54.1     12.7

The x models cost 4.5x the speed for about 10 points of mAP on a 13 TOPS
Hailo-8L. The spare throughput is not waste, it is the budget for speech,
ToF fusion, OCR and the assistant running at the same time. See MEMORY.md.

THE LAST STEP IS NOT HERE
-------------------------
ONNX is not what the Hailo runs. Converting ONNX to .hef needs the Hailo
Dataflow Compiler, which is x86_64 Linux only and sits behind a free Hailo
Developer Zone login. That step runs in WSL2 Ubuntu. This script stops at
ONNX and prints what to do next.
"""
import argparse
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="path to smartcane.yaml")
    ap.add_argument("--model", default="yolov8s.pt",
                    help="starting weights. yolov8s matches what we benchmarked")
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--imgsz", type=int, default=640,
                    help="must match the input size compiled into the .hef")
    ap.add_argument("--batch", type=int, default=12,
                    help="12 fits an 8 GB RTX 4060 at 640px with yolov8s. "
                         "Drop to 8 if you hit CUDA out of memory.")
    ap.add_argument("--name", default="smartcane")
    ap.add_argument("--optimizer", default="auto",
                    help="auto lets Ultralytics choose (8.4 picks MuSGD for long runs). "
                         "SGD measured faster on the laptop: MuSGD's step took ~30%% of "
                         "the CPU-bound main process (py-spy, 3 Oct 2026)")
    ap.add_argument("--resume", action="store_true")
    # Fine-tune controls (4 Oct 2026). The v2 run fell from mAP50 0.40 to 0.22
    # once warm-up ended at lr0 0.01, so the v3 run restarts from the best
    # checkpoint with a lower, cosine-decaying rate and a hard time budget.
    ap.add_argument("--lr0", type=float, default=0.01)
    ap.add_argument("--lrf", type=float, default=0.01)
    ap.add_argument("--cos-lr", action="store_true")
    ap.add_argument("--warmup-epochs", type=float, default=3.0)
    ap.add_argument("--close-mosaic", type=int, default=10)
    ap.add_argument("--patience", type=int, default=25)
    ap.add_argument("--time", type=float, default=None,
                    help="hours. Ultralytics fits the run (and its LR schedule) "
                         "into this budget, overriding --epochs")
    ap.add_argument("--export", action="store_true",
                    help="skip training, just export existing weights to ONNX")
    ap.add_argument("--weights", default="",
                    help="weights to export when using --export")
    args = ap.parse_args()

    try:
        import torch
        from ultralytics import YOLO
    except ImportError as e:
        sys.exit(f"missing dependency: {e}\n"
                 f"  C:/ml/venv/Scripts/python.exe -m pip install ultralytics")

    if not torch.cuda.is_available():
        print("WARNING: CUDA not available. Training on CPU will take weeks.")
        print("         Check nvidia-smi and the torch build.")
    else:
        print(f"GPU: {torch.cuda.get_device_name(0)} "
              f"({torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB)")

    if args.export:
        weights = args.weights or f"runs/detect/{args.name}/weights/best.pt"
        if not Path(weights).exists():
            sys.exit(f"no weights at {weights}")
        model = YOLO(weights)
    else:
        data = Path(args.data)
        if not data.exists():
            sys.exit(f"no dataset descriptor at {data}\n"
                     f"  run prepare_datasets.py first")
        model = YOLO(args.model)
        print(f"training {args.model} on {data} for {args.epochs} epochs")
        model.train(
            data=str(data),
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            device=0,
            name=args.name,
            resume=args.resume,
            optimizer=args.optimizer,
            # Augmentation tuned for a body-worn camera on a street, not for
            # a benchmark leaderboard.
            degrees=10.0,      # the camera rolls when a cane swings
            translate=0.1,
            scale=0.5,
            fliplr=0.5,
            mosaic=1.0,
            close_mosaic=args.close_mosaic,   # last 10 epochs without mosaic, steadier boxes
            hsv_v=0.5,         # Indian sunlight to deep shade is a huge range
            patience=args.patience,
            lr0=args.lr0,
            lrf=args.lrf,
            cos_lr=args.cos_lr,
            warmup_epochs=args.warmup_epochs,
            time=args.time,
            amp=True,
        )
        weights = f"runs/detect/{args.name}/weights/best.pt"
        model = YOLO(weights)

    # opset 11 is what the Hailo Dataflow Compiler is happiest with.
    # simplify=True removes graph nodes the parser tends to choke on.
    print("exporting to ONNX ...")
    onnx = model.export(format="onnx", imgsz=args.imgsz, opset=11,
                        simplify=True, dynamic=False)
    print(f"\nONNX written: {onnx}")

    print(f"""
NEXT STEP, in WSL2 Ubuntu (not Windows, not the Pi):

  1. Install the Hailo Dataflow Compiler .whl from the Hailo Developer Zone.
  2. Compile, telling it where a calibration set of ~1000 real images lives:

       hailomz compile yolov8s \\
           --ckpt {Path(onnx).name} \\
           --hw-arch hailo8l \\
           --calib-path /path/to/calibration/images \\
           --classes <your class count>

  3. Copy the resulting .hef to the Pi:

       scp yolov8s.hef pi@192.168.3.51:/home/pi/smartcane/models/

  4. Point detect.py at it:

       python3 detect.py --model /home/pi/smartcane/models/yolov8s.hef \\
                         --labels /home/pi/smartcane/models/classes.txt

--hw-arch MUST be hailo8l. Our board is the 13 TOPS variant, confirmed by
hailortcli. A hef built for hailo8 will not load.
""")


if __name__ == "__main__":
    main()
