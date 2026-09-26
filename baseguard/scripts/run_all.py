"""Assess every frame with the agent and store the results in the brief cache (what the UI shows).

usage: python -m scripts.run_all [--fresh]
"""
import argparse
import time
from concurrent.futures import ThreadPoolExecutor

from agent.runner import assess
from core.data import images


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="re-run frames that already have an assessment")
    a = ap.parse_args()
    ids = sorted(images(), key=lambda k: images()[k].time)
    t0 = time.time()

    def one(i):
        try:
            out = assess(i, use_cache=not a.fresh)
            b = out["brief"]
            print(f"  ✓ {i} {b['action']} · {out['usage']['seconds']} sn · denetim turu {out.get('audit_rounds', 0)}"
                  f" · kalan uyarı {len(b.get('audit') or [])}", flush=True)
        except Exception as ex:
            print(f"  ✗ {i}: {type(ex).__name__}: {ex}", flush=True)

    print(f"{len(ids)} kare", flush=True)
    with ThreadPoolExecutor(3) as ex:
        list(ex.map(one, ids))
    print(f"bitti: {time.time() - t0:.0f} sn", flush=True)


if __name__ == "__main__":
    main()
