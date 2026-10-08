# smartcane152_v3

YOLO11s, 152 classes, trained on merged_v2 (see docs/training.md).
Validation on 27,906 images: mAP50 0.535, mAP50-95 0.376.

| File | Use |
|---|---|
| `smartcane152_v3_h8l.hef` | Compiled for the Hailo-8L (HailoRT 4.23). What runs on the cane |
| `smartcane152_v3_best.pt` | PyTorch weights (Ultralytics 8.4.155), best epoch 24 |
| `smartcane152_v3.onnx` | ONNX export, opset 11, 640x640, input to the Hailo compile |
| `smartcane152.txt` | Class names in model order |
| `smartcane152_v3.alls`, `nms_config.json` | Hailo DFC 3.34 compile script and NMS settings |

On the cane:

```bash
python3 detect.py --model smartcane152_v3_h8l.hef --labels smartcane152.txt --all-classes
```

On a PC with Ultralytics:

```python
from ultralytics import YOLO
YOLO("smartcane152_v3_best.pt").predict("street.jpg", conf=0.25)
```
