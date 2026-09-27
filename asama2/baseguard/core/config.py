"""Paths and tunable thresholds, in one place."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # baseguard/
DATA_DIR = Path(os.getenv("BG_DATA_DIR", ROOT.parent))  # stage2/ (given data files)

IMAGES_DIR = DATA_DIR / "images"
IMAGE_META = DATA_DIR / "image_meta.json"
ZONES = DATA_DIR / "zones.json"
TRACKS = DATA_DIR / "tracks.csv"
REPORTS = DATA_DIR / "field_reports.json"
WEIGHTS_DIR = DATA_DIR / "model" / "weights"

CACHE_DIR = ROOT / "cache"
DETECTIONS_CACHE = CACHE_DIR / "detections.json"
BRIEFS_DIR = CACHE_DIR / "briefs"

# detection
DET_MIN_CONF = 0.30          # below this a box is not treated as a vehicle
DET_CACHE_MIN_CONF = 0.05    # what we keep in the cache (lets us re-tune without re-running)
DET_DEDUP_IOU = 0.70         # multi-label NMS can emit car+van for one box -> keep best

# track matching: gate = max(MIN_M, PX * metres-per-pixel)
MATCH_GATE_MIN_M = 8.0
MATCH_GATE_PX = 40.0

# reports
REPORT_RADIUS_M = 250.0      # coordinate report considered "about" an image if within this of its footprint
REPORT_LOOKBACK_MIN = 180    # only reports from the last 3h before capture
