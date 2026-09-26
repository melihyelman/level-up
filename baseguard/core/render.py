"""Annotated frames and crops (shared by the agent's vision input and the UI)."""
from __future__ import annotations

import base64
from pathlib import Path

import cv2
import numpy as np


ACTION_BGR = {"hemen teyit/müdahale": (40, 40, 230), "izlemeye al": (0, 170, 255), "işlem gerekmez": (170, 170, 170)}


NEUTRAL = (230, 200, 60)  # cyan-ish: not yet assessed


def annotate(scene, decisions: dict | None = None, max_w: int = 1280, show_reports: bool = True,
             min_conf: float = 0.0) -> np.ndarray:
    """Draw detections (D#), track-only positions (T####) and report points (R###).

    `decisions` maps D#/T#### -> action as decided by the agent; without it everything is neutral.
    Weak boxes (conf < 0.3) are dotted.
    """
    decisions = decisions or {}
    im = cv2.imread(str(scene.image_path))
    H, W = im.shape[:2]
    lw = max(1, round(W / 640))
    fs = 0.45 * W / 960

    def label(text, tx, ty, col):
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, fs, 1)
        cv2.rectangle(im, (tx, ty - th - 3), (tx + tw + 4, ty + 2), (20, 20, 20), -1)
        cv2.putText(im, text, (tx + 2, ty), cv2.FONT_HERSHEY_SIMPLEX, fs, col, 1, cv2.LINE_AA)

    tm = scene.track_matches()
    for d in scene.detections()["detections"]:
        if d["conf"] < min_conf:
            continue
        tid = next((r["track_id"] for r in tm["matches"] if r["detection"] == d["id"]), None)
        col = ACTION_BGR.get(decisions.get(d["id"]) or decisions.get(tid), NEUTRAL)
        x, y, w, h = map(int, d["box_xywh"])
        if d["conf"] < 0.3:
            for i in range(x, x + w, 6):
                cv2.line(im, (i, y), (min(i + 3, x + w), y), col, lw); cv2.line(im, (i, y + h), (min(i + 3, x + w), y + h), col, lw)
            for j in range(y, y + h, 6):
                cv2.line(im, (x, j), (x, min(j + 3, y + h)), col, lw); cv2.line(im, (x + w, j), (x + w, min(j + 3, y + h)), col, lw)
        else:
            cv2.rectangle(im, (x, y), (x + w, y + h), col, lw)
        label(f"{d['id']} {d['cls']} {d['conf']:.2f}", x, max(12, y - 4), col)
    for t in tm["tracks_in_frame_without_detection"]:
        col = ACTION_BGR.get(decisions.get(t["track_id"]), NEUTRAL)
        cx, cy = t["center_px"]
        cv2.circle(im, (cx, cy), int(12 * W / 960), col, lw)
        label(f"{t['track_id']} ?", cx + 8, cy - 8, col)
    if show_reports:
        for r in scene.reports()["reports"]:
            if r.get("point_px") and 0 <= r["point_px"][0] < W and 0 <= r["point_px"][1] < H:
                x, y = r["point_px"]
                s = int(7 * W / 960)
                cv2.drawMarker(im, (x, y), (255, 120, 255), cv2.MARKER_TILTED_CROSS, 2 * s, lw)
                cv2.putText(im, r["rid"], (x + s, y + s + 8), cv2.FONT_HERSHEY_SIMPLEX, fs * 0.85, (255, 120, 255), 1, cv2.LINE_AA)
    if W > max_w:
        im = cv2.resize(im, (max_w, int(H * max_w / W)), interpolation=cv2.INTER_AREA)
    return im


def raw_frame(scene, max_w: int = 1280) -> np.ndarray:
    """The frame without any overlay, downscaled for the LLM."""
    im = cv2.imread(str(scene.image_path))
    H, W = im.shape[:2]
    if W > max_w:
        im = cv2.resize(im, (max_w, int(H * max_w / W)), interpolation=cv2.INTER_AREA)
    return im


def crop(image_path: Path, center_px: list[int], box: list[float] | None, pad: float = 1.5, min_size: int = 96) -> np.ndarray:
    im = cv2.imread(str(image_path))
    H, W = im.shape[:2]
    cx, cy = center_px
    if box:
        half = max(box[2], box[3]) * pad / 2 + 10
    else:
        half = 40
    half = max(half, min_size / 2)
    x1, y1 = int(max(0, cx - half)), int(max(0, cy - half))
    x2, y2 = int(min(W, cx + half)), int(min(H, cy + half))
    c = im[y1:y2, x1:x2]
    scale = 256 / max(c.shape[:2])
    if scale > 1:
        c = cv2.resize(c, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return c


def to_data_url(im: np.ndarray, quality: int = 85) -> str:
    ok, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def to_rgb(im: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(im, cv2.COLOR_BGR2RGB)
