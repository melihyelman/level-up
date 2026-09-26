"""Command-line demo.

  python cli.py img_000860            # the agent assesses one frame, streaming its tool calls
  python cli.py img_000860 --fresh    # ignore the cached assessment
  python cli.py img_000860 --facts    # only the measurements the tools would return (no LLM)
  python cli.py --all                 # assess every frame, print the agent's ranking
  python cli.py --budget              # remaining GLM budget
"""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor

from agent import llm_client
from agent.runner import DEFAULT_EFFORT, assess
from agent.tools import ACTIONS
from core.data import images
from core.scene import Scene

COL = {"hemen teyit/müdahale": "\033[91m", "izlemeye al": "\033[33m", "işlem gerekmez": "\033[90m"}
RST, B, DIM = "\033[0m", "\033[1m", "\033[2m"


def show(ev):
    k, t, d = ev["kind"], ev["title"], ev["detail"]
    if k == "tool_call":
        print(f"\n{B}🛠  {t}{RST}({json.dumps(d, ensure_ascii=False) if d else ''})")
    elif k == "tool_result":
        print(f"{DIM}   ← {d[:400]}{'…' if len(d) > 400 else ''}{RST}")
    elif k == "say":
        print(f"\n💬 {d}")
    elif k == "warn":
        print(f"\n⚠️  {t}: {d}")
    elif k == "audit":
        print(f"\n🔎 {t}" + "".join(f"\n   - {x}" for x in d))


def print_brief(b):
    act = b["action"]
    print(f"\n{COL[act]}■ {act.upper()}{RST}  {B}{b['headline']}{RST}\n\n{b['brief']}\n")
    for v in b.get("vehicles", []):
        tid = f" ({v['track_id']})" if v.get("track_id") and v["track_id"] != v["id"] else ""
        print(f"  {COL[v['action']]}{v['id']}{tid} [{v['action']} · güven {v['confidence']}]{RST} {v['reason']}")
        if v.get("evidence"):
            print(f"      dayanak: {', '.join(v['evidence'])}")
    for r in b.get("reports", []):
        print(f"  {r['rid']}: {r['verdict']} — {r['reason']}")
        for c in r.get("claims_checked", []):
            print(f"      · {c.get('claim')}: {c.get('finding')}")
    for u in b.get("uncertainties", []):
        print(f"  ? {u}")
    for a in b.get("audit", []):
        print(f"  ⚠️ denetim: {a}")


def facts(image_id):
    s = Scene(image_id)
    for name, res in [("get_image_info", s.info()), ("detect_vehicles", s.detections()),
                      ("match_tracks", s.track_matches()), ("get_reports", s.reports())]:
        print(f"\n{B}{name}{RST}\n{json.dumps(res, ensure_ascii=False, indent=1, default=list)}")
    for r in s.track_matches()["matches"]:
        if r["track_id"]:
            print(f"\n{B}get_motion {r['track_id']}{RST}\n{json.dumps(s.motion(r['track_id']), ensure_ascii=False, default=list)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image_id", nargs="?")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--facts", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--effort", default=DEFAULT_EFFORT, choices=["low", "high", "max"])
    ap.add_argument("--budget", action="store_true")
    a = ap.parse_args()

    if a.budget:
        print(llm_client.budget_info())
    elif a.facts:
        facts(a.image_id)
    elif a.all:
        ids = sorted(images(), key=lambda k: images()[k].time)
        with ThreadPoolExecutor(3) as ex:
            outs = list(ex.map(lambda i: assess(i, effort=a.effort, use_cache=not a.fresh), ids))
        for o in sorted(outs, key=lambda o: (ACTIONS.index(o["brief"]["action"]), images()[o["image_id"]].time)):
            b = o["brief"]
            print(f"{images()[o['image_id']].time} {o['image_id']} {COL[b['action']]}{b['action']:22}{RST} {b['headline']}")
    else:
        out = assess(a.image_id, cb=show, effort=a.effort, use_cache=not a.fresh)
        print_brief(out["brief"])
        print(f"\n{DIM}kullanım: {out['usage']}{RST}")


if __name__ == "__main__":
    try:
        main()
    except llm_client.LLMUnavailable as ex:
        print(f"⚠️  {ex}. .env dosyasına GLM_API_KEY ekleyin; ölçümleri görmek için --facts kullanın.")
