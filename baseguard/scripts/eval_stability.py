"""Run the agent repeatedly on the same frames and measure how stable and well-grounded it is.

No ground truth exists for this data, so this measures consistency, not accuracy:
  - action agreement between repeats (full action, and "müdahale or not")
  - coverage: share of required vehicles that got a decision
  - schema retries, audit rounds, audit warnings left, time, tokens

usage:
  python -m scripts.eval_stability --name v2 [--frames ...] [--reps 2]
  python -m scripts.eval_stability --name v2 --compare cache/experiments/output_modes/action
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
from pathlib import Path

from agent.runner import assess
from core import config
from core.scene import Scene

ROOT = config.CACHE_DIR / "experiments"
FRAMES = ["img_000860", "img_005788", "img_003464", "img_003189", "img_006388", "img_003880"]


def decisions(run: dict) -> dict[str, str]:
    """id -> action, for both the current keyed/normalised format and the earlier list format."""
    out = {}
    for v in run["brief"].get("vehicles", []):
        for k in (v.get("id"), v.get("track_id")):
            if k:
                out[k] = v.get("action")
    return out


def load(directory: Path, frames, reps) -> dict:
    return {(r, f): json.loads(p.read_text()) for r in range(1, reps + 1) for f in frames
            if (p := directory / f"rep{r}" / f"{f}.json").exists()}


def metrics(runs: dict, frames, reps) -> dict:
    same = same_urgent = total = 0
    cov = []
    for f in frames:
        req = Scene(f).subjects()[0]
        rr = [runs[(r, f)] for r in range(1, reps + 1) if (r, f) in runs]
        for run in rr:
            d = decisions(run)
            cov.append(sum(v in d for v in req) / len(req))
        for a, b in combinations(rr, 2):
            da, db = decisions(a), decisions(b)
            for v in req:
                total += 1
                same += da.get(v) == db.get(v)
                same_urgent += (da.get(v) == "hemen teyit/müdahale") == (db.get(v) == "hemen teyit/müdahale")
    allr = list(runs.values())
    n = len(allr) or 1
    flagged = [x == "hemen teyit/müdahale" for run in allr for x in decisions(run).values()]
    return dict(
        runs=len(allr),
        action_agreement=round(same / total, 3) if total else None,
        urgent_agreement=round(same_urgent / total, 3) if total else None,
        urgent_share=round(sum(flagged) / len(flagged), 3) if flagged else None,
        coverage=round(sum(cov) / len(cov), 3) if cov else None,
        schema_retries_per_run=round(sum(sum(e["kind"] == "warn" for e in r["trace"]) for r in allr) / n, 2),
        audit_rounds_per_run=round(sum(r.get("audit_rounds", 0) for r in allr) / n, 2),
        audit_warnings_left=sum(len(r["brief"].get("audit") or []) for r in allr),
        avg_seconds=round(sum(r["usage"]["seconds"] for r in allr) / n, 1),
        avg_llm_calls=round(sum(r["usage"]["calls"] for r in allr) / n, 1),
        avg_prompt_tokens=round(sum(r["usage"]["prompt_tokens"] for r in allr) / n),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--frames", nargs="*", default=FRAMES)
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--compare", type=Path, help="an earlier experiment directory with rep1/, rep2/")
    ap.add_argument("--report-only", action="store_true")
    a = ap.parse_args()
    out = ROOT / a.name

    if not a.report_only:
        jobs = [(r, f) for r in range(1, a.reps + 1) for f in a.frames if not (out / f"rep{r}" / f"{f}.json").exists()]
        print(f"{len(jobs)} çalıştırma", flush=True)

        def one(job):
            r, f = job
            try:
                assess(f, use_cache=False, save_dir=out / f"rep{r}")
                print(f"  ✓ rep{r} {f}", flush=True)
            except Exception as ex:
                print(f"  ✗ rep{r} {f}: {ex}", flush=True)

        with ThreadPoolExecutor(3) as ex:
            list(ex.map(one, jobs))

    res = {a.name: metrics(load(out, a.frames, a.reps), a.frames, a.reps)}
    if a.compare:
        res[a.compare.name + " (önceki)"] = metrics(load(a.compare, a.frames, a.reps), a.frames, a.reps)
    keys = list(next(iter(res.values())))
    lines = ["| ölçüt | " + " | ".join(res) + " |", "|---|" + "---|" * len(res)]
    lines += [f"| {k} | " + " | ".join(str(v[k]) for v in res.values()) + " |" for k in keys]
    md = "\n".join(lines)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
