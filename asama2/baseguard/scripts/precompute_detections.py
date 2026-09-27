"""Run the full stage-1 blend over all images and cache the raw boxes.

usage: python -m scripts.precompute_detections [--mode full|fast] [--limit N]
"""
import argparse
import time

from stage2.asama2.baseguard.core import config
from stage2.asama2.baseguard.core.detect import detect_images, save_cache, FAST_CACHE


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="full", choices=["full", "fast"])
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    paths = sorted(config.IMAGES_DIR.glob("*.jpg"))
    if a.limit:
        paths = paths[: a.limit]
    t = time.time()
    res = detect_images(paths, mode=a.mode, log=lambda m: print(m, flush=True))
    save_cache(res, config.DETECTIONS_CACHE if a.mode == "full" else FAST_CACHE)
    n = sum(len(v) for v in res.values())
    print(f"done: {len(res)} images, {n} raw boxes, {time.time() - t:.0f}s", flush=True)


if __name__ == "__main__":
    main()
