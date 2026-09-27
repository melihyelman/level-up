"""Vehicle detection with the stage-1 models.

Two modes:
  full : the exact stage-1 submission blend (3 YOLO26 models, per-model TTA, WBF 3:1:1).
         Slow on a laptop, so it is run once over all images and cached.
  fast : the strongest single model at base size, single view. Used for images that are
         not in the cache (live demo on a new frame).

Blend logic mirrors model/infer_blend.py; only the device handling differs (MPS/CPU, no fp16).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

import cv2
import numpy as np

from . import config

CLASSES = ["car", "van", "truck", "bus"]

# per model: file, base imgsz, tta views (zoom, hflip, ultralytics augment), blend weight
MODELS = [
    dict(name="night", file="night_l1536.pt", base=1536, w=3,
         views=[(1, 0, 0), (1, 1, 0), (1.1, 0, 0), (1.25, 0, 0), (1.75, 0, 0), (2.0, 0, 0), (1, 0, 1), (1.25, 1, 0)]),
    dict(name="carunder", file="carunder_m1280.pt", base=1280, w=1,
         views=[(1, 0, 0), (1, 1, 0), (1.25, 0, 0)]),
    dict(name="patch", file="patch_m1280.pt", base=1280, w=1,
         views=[(1, 0, 0)]),
]
VIEW_WBF_IOU = 0.65
BLEND_WBF_IOU = 0.65
MIN_AREA = 100  # px^2


@dataclass
class Detection:
    cls: str
    conf: float
    x: float  # top-left, pixels
    y: float
    w: float
    h: float

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    @property
    def xyxy(self) -> tuple[float, float, float, float]:
        return self.x, self.y, self.x + self.w, self.y + self.h


def _device() -> str:
    import torch
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


_patched = False


def _patch_multilabel_nms():
    # multi-label NMS: one box may keep both car and van scores (+1.8 mAP50 on val in stage 1)
    global _patched
    if _patched:
        return
    import ultralytics.utils.nms as NMS
    orig = NMS.non_max_suppression
    NMS.non_max_suppression = lambda *a, **k: orig(*a, **{**k, "multi_label": True})
    _patched = True


def _px(base, z):
    return int(round(base * z / 32) * 32)


def _predict_view(model, images, imgsz, flip, ultra, device):
    out = []
    extra = {"half": True} if device == "cuda" else {}
    for im in images:
        src = np.ascontiguousarray(im[:, ::-1]) if flip else im
        r = model.predict(src, imgsz=imgsz, conf=0.001, iou=0.6, max_det=1000,
                          augment=bool(ultra), verbose=False, nms=True, device=device, **extra)[0]
        H, W = im.shape[:2]
        xy = r.boxes.xyxy.cpu().numpy().copy()
        if flip:
            xy[:, [0, 2]] = W - xy[:, [2, 0]]
        out.append(((xy / np.array([W, H, W, H])).clip(0, 1),
                    r.boxes.conf.cpu().numpy(), r.boxes.cls.cpu().numpy()))
    return out


def _run_model(cfg, images, device, views=None):
    from ultralytics import YOLO
    from ensemble_boxes import weighted_boxes_fusion

    model = YOLO(str(config.WEIGHTS_DIR / cfg["file"]))
    views = views or cfg["views"]
    per_view = [_predict_view(model, images, _px(cfg["base"], z), fl, ua, device) for z, fl, ua in views]
    fused = []
    for i in range(len(images)):
        B = [v[i][0] for v in per_view]; S = [v[i][1] for v in per_view]; L = [v[i][2] for v in per_view]
        if len(per_view) == 1:
            fused.append((B[0], S[0], L[0]))
        elif any(len(s) for s in S):
            b, s, l = weighted_boxes_fusion(B, S, L, iou_thr=VIEW_WBF_IOU, skip_box_thr=0.001, conf_type="avg")
            fused.append((np.asarray(b), np.asarray(s), np.asarray(l)))
        else:
            fused.append((np.zeros((0, 4)), np.zeros(0), np.zeros(0)))
    return fused


def _to_detections(b, s, l, W, H, min_conf) -> list[Detection]:
    dets = []
    for (x1, y1, x2, y2), c, k in zip(b, s, l):
        x, y, w, h = x1 * W, y1 * H, (x2 - x1) * W, (y2 - y1) * H
        if w * h >= MIN_AREA and c >= min_conf:
            dets.append(Detection(CLASSES[int(k)], round(float(c), 4),
                                  round(float(x), 1), round(float(y), 1), round(float(w), 1), round(float(h), 1)))
    return dets


def detect_images(paths: list[Path], mode: str = "full", min_conf: float = config.DET_CACHE_MIN_CONF,
                  log=print) -> dict[str, list[Detection]]:
    """Run detection over images; returns {image_id: [Detection]} (raw, not deduplicated)."""
    from ensemble_boxes import weighted_boxes_fusion

    _patch_multilabel_nms()
    device = _device()
    images = [cv2.imread(str(p)) for p in paths]
    ids = [Path(p).stem for p in paths]

    if mode == "fast":
        cfg = MODELS[0]
        log(f"[detect] fast mode, {cfg['name']} on {device}")
        res = _run_model(cfg, images, device, views=[(1, 0, 0)])
        return {i: _to_detections(*r, im.shape[1], im.shape[0], min_conf) for i, r, im in zip(ids, res, images)}

    per_model = []
    for cfg in MODELS:
        log(f"[detect] {cfg['name']}: {len(cfg['views'])} views x {len(images)} images on {device}")
        per_model.append(_run_model(cfg, images, device))
    weights = [cfg["w"] for cfg in MODELS]

    out = {}
    for n, (iid, im) in enumerate(zip(ids, images)):
        H, W = im.shape[:2]
        B, S, L = [], [], []
        for m in per_model:
            b, s, l = m[n]
            keep = (b[:, 2] - b[:, 0]) * W * (b[:, 3] - b[:, 1]) * H >= MIN_AREA if len(b) else np.zeros(0, bool)
            B.append(b[keep]); S.append(s[keep]); L.append(l[keep])
        if not any(len(s) for s in S):
            out[iid] = []
            continue
        b, s, l = weighted_boxes_fusion(B, S, L, weights=weights, iou_thr=BLEND_WBF_IOU,
                                        skip_box_thr=0.0002, conf_type="avg")
        out[iid] = _to_detections(b, s, l, W, H, min_conf)
    return out


# ---------------------------------------------------------------- post-processing

def _iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a.xyxy; bx1, by1, bx2, by2 = b.xyxy
    iw = max(0.0, min(ax2, bx2) - max(ax1, bx1)); ih = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    return inter / (a.w * a.h + b.w * b.h - inter + 1e-9)


def clean(dets: list[Detection], min_conf: float = config.DET_MIN_CONF,
          dedup_iou: float = config.DET_DEDUP_IOU) -> list[Detection]:
    """Confidence filter + class-agnostic dedup (multi-label NMS emits car AND van for one vehicle)."""
    kept: list[Detection] = []
    for d in sorted((d for d in dets if d.conf >= min_conf), key=lambda d: -d.conf):
        if all(_iou(d, k) < dedup_iou for k in kept):
            kept.append(d)
    return kept


# ---------------------------------------------------------------- cache

FAST_CACHE = config.CACHE_DIR / "detections_fast.json"


def load_cache(path: Path = config.DETECTIONS_CACHE) -> dict[str, list[Detection]]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    return {k: [Detection(**d) for d in v] for k, v in raw.items()}


def save_cache(dets: dict[str, list[Detection]], path: Path = config.DETECTIONS_CACHE):
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cur = json.loads(path.read_text()) if path.exists() else {}
    cur.update({k: [asdict(d) for d in v] for k, v in dets.items()})
    path.write_text(json.dumps(cur, indent=0))


def get_detections(image_id: str, image_path: Path | None = None) -> tuple[list[Detection], str]:
    """Cleaned detections for an image; cache first, fast live inference otherwise. Returns (dets, source)."""
    cache = load_cache()
    if image_id in cache:
        return clean(cache[image_id]), "full-blend (cached)"
    fast = load_cache(FAST_CACHE)
    if image_id in fast:
        return clean(fast[image_id]), "fast (cached)"
    path = image_path or config.IMAGES_DIR / f"{image_id}.jpg"
    res = detect_images([path], mode="fast")
    save_cache(res, FAST_CACHE)
    return clean(res[image_id]), "fast (live)"
