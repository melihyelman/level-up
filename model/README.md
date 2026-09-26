# Roketsan Level Up AI – vehicle detection model (inference package)

Trained and ready: no training needed. The package contains the 3 finished models and one inference script that reproduces our final submission (**public leaderboard 0.79722**, validation mAP50 **0.8806**).

Detects 4 classes in drone images: **car, van, truck, bus**.

## Contents

| file | what |
|---|---|
| `infer_blend.py` | inference script: images in, predictions CSV out |
| `weights/night_l1536.pt` | YOLO26-L, input 1536 px |
| `weights/carunder_m1280.pt` | YOLO26-M, input 1280 px |
| `weights/patch_m1280.pt` | YOLO26-M, input 1280 px |
| `requirements.txt` | python packages |

All models are Ultralytics YOLO26, initialized from the official COCO-pretrained weights.

## Run

```bash
pip install -r requirements.txt

# any folder of images (.jpg / .png)
python infer_blend.py --test_dir <image folder> --weights weights --out predictions.csv

# competition test set, rows in sample_submission order
python infer_blend.py --test_dir <test/images> --sample <sample_submission.csv> --weights weights --out submission.csv
```

A GPU is strongly recommended: about 1 h for the 2118 competition test images on an A100. On CPU it works, but takes minutes per image.

## Output

One row per image: `image_id,PredictionString`. `PredictionString` holds `label conf x y w h` for each detected vehicle (x, y = top-left corner, pixels), or `none` if nothing is found. Boxes down to confidence 0.001 are kept, as usual for mAP scoring. Filter by `conf` (e.g. ≥ 0.3) for a clean visual result.

## How a prediction is made

1. **Each model predicts the image several times (test-time augmentation):**
   - night model: 8 views. Scale 1.0 / 1.1 / 1.25 / 1.75 / 2.0 of 1536 px, horizontal flip at 1.0 and 1.25, Ultralytics built-in augment.
   - carunder model: 3 views. 1280 px, flipped 1280 px, 1600 px.
   - patch model: 1 view at 1280 px.

   The views of one model are merged with Weighted Box Fusion (WBF, IoU 0.65). Enlarged views help with the many very small vehicles.
2. **The 3 models are blended** with WBF, weights **3 : 1 : 1** (night : carunder : patch), IoU 0.65. The weights were learned on a held-out validation set.
3. Boxes smaller than 100 px² are dropped.

Per-view settings: confidence 0.001, NMS IoU 0.6, up to 1000 boxes, multi-label NMS (one box can keep both car and van scores).

## Accuracy (validation, 647 held-out images, mAP50)

| | mAP50 | car | van | truck | bus |
|---|---|---|---|---|---|
| patch model | 0.8432 | .919 | .737 | .818 | .900 |
| carunder model + TTA | 0.8598 | .927 | .761 | .842 | .909 |
| night model + TTA | 0.8748 | .932 | .786 | .860 | .922 |
| **final blend** | **0.8806** | .936 | .792 | .866 | .928 |

Re-running the script reproduces the submitted CSV up to GPU non-determinism and 5-decimal rounding.
