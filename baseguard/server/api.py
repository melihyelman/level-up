"""HTTP API for the web UI.

  uvicorn server.api:app --port 8000

Measurements come from core.Scene, decisions only from the agent's stored assessments. Agent runs
and replays are streamed as Server-Sent Events, one JSON object per trace event.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from agent import llm_client
from agent.chat import answer
from agent.runner import assess, cached
from agent.tools import ACTIONS
from core.data import images, zones
from core.render import crop
from core.scene import Scene

import cv2

app = FastAPI(title="BaseGuard API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_running: set[str] = set()
_lock = threading.Lock()


@lru_cache(maxsize=64)
def scene(image_id: str) -> Scene:
    if image_id not in images():
        raise HTTPException(404, f"{image_id} yok")
    return Scene(image_id)


def _assessment_summary(a: dict | None) -> dict | None:
    if not a:
        return None
    b = a["brief"]
    return dict(action=b["action"], headline=b["headline"],
                urgent=sum(v["action"] == ACTIONS[0] for v in b["vehicles"]),
                watch=sum(v["action"] == ACTIONS[1] for v in b["vehicles"]),
                contradicted=sum(r.get("verdict") == "tespitle çelişiyor" for r in b.get("reports", [])))


# ---------------------------------------------------------------- read

@app.get("/api/overview")
def overview():
    base, base_name, zs = zones()
    frames = []
    for iid in sorted(images(), key=lambda k: images()[k].time):
        s = scene(iid)
        info = s.info()
        frames.append(dict(
            id=iid, time=info["capture_time"], zone=info["nearest_zone"], dist_to_base_m=info["dist_to_base_m"],
            direction=info["direction_from_base"], center=info["center"], corners=info["corners"],
            footprint_m=info["footprint_m"], vehicles=len(s.subjects()[0]),
            assessment=_assessment_summary(cached(iid))))
    assessed = [f for f in frames if f["assessment"]]
    return dict(
        base=dict(name=base_name, lat=base[0], lon=base[1]),
        zones=[dict(name=z.name, lat=z.center[0], lon=z.center[1]) for z in zs],
        llm=dict(available=llm_client.available(), model=llm_client.MODEL),
        frames=frames,
        stats=dict(frames=len(frames), assessed=len(assessed),
                   urgent_frames=sum(f["assessment"]["action"] == ACTIONS[0] for f in assessed),
                   watch_frames=sum(f["assessment"]["action"] == ACTIONS[1] for f in assessed),
                   urgent_vehicles=sum(f["assessment"]["urgent"] for f in assessed),
                   contradicted_reports=sum(f["assessment"]["contradicted"] for f in assessed)))


@app.get("/api/frames/{image_id}")
def frame(image_id: str):
    s = scene(image_id)
    a = cached(image_id)
    decisions = {v["id"]: v for v in a["brief"]["vehicles"]} if a else {}
    tm = s.track_matches()
    by_det = {r["detection"]: r for r in tm["matches"]}
    required, optional = s.subjects()

    vehicles = []
    for d in s.detections()["detections"]:
        m = by_det.get(d["id"], {})
        tid = m.get("track_id")
        vehicles.append(dict(id=d["id"], kind="detection", cls=d["cls"], conf=d["conf"], box=d["box_xywh"],
                             center_px=d["center_px"], lat=d["lat"], lon=d["lon"], dist_to_base_m=d["dist_to_base_m"],
                             track_id=tid, match_dist_m=m.get("dist_m"), required=d["id"] in required,
                             motion=s.motion(tid, with_polyline=True) if tid else None,
                             decision=decisions.get(d["id"])))
    for t in tm["tracks_in_frame_without_detection"]:
        mo = s.motion(t["track_id"], with_polyline=True)
        vehicles.append(dict(id=t["track_id"], kind="track_only", cls=None, conf=None, box=None,
                             center_px=t["center_px"], lat=t["lat"], lon=t["lon"],
                             dist_to_base_m=mo["dist_to_base_now_m"], track_id=t["track_id"], match_dist_m=None,
                             required=True, motion=mo, decision=decisions.get(t["track_id"])))

    verdicts = {r["rid"]: r for r in a["brief"].get("reports", [])} if a else {}
    reports = [dict(r, agent=verdicts.get(r["rid"])) for r in s.reports()["reports"]]
    return dict(
        info=s.info(), vehicles=vehicles, reports=reports,
        tracks_just_outside=tm["tracks_just_outside_frame"],
        assessment=None if not a else dict(
            brief=a["brief"], usage=a["usage"], effort=a.get("effort"), model=a.get("model"),
            audit_rounds=a.get("audit_rounds", 0), created=a.get("created"),
            steps=sum(e["kind"] == "tool_call" for e in a["trace"])),
        running=image_id in _running)


@app.get("/api/frames/{image_id}/trace")
def frame_trace(image_id: str):
    a = cached(image_id)
    return a["trace"] if a else []


@app.get("/api/frames/{image_id}/image")
def frame_image(image_id: str):
    return FileResponse(scene(image_id).image_path, media_type="image/jpeg",
                        headers={"Cache-Control": "max-age=86400"})


@app.get("/api/frames/{image_id}/crop/{target}")
def frame_crop(image_id: str, target: str):
    s = scene(image_id)
    d = s.detection(target)
    if d:
        center, box = d["center_px"], d["box_xywh"]
    else:
        t = next((t for t in s.track_matches()["tracks_in_frame_without_detection"] if t["track_id"] == target), None)
        if not t:
            raise HTTPException(404, target)
        center, box = t["center_px"], None
    ok, buf = cv2.imencode(".jpg", crop(s.image_path, center, box), [cv2.IMWRITE_JPEG_QUALITY, 88])
    return Response(buf.tobytes(), media_type="image/jpeg")


# ---------------------------------------------------------------- agent streams

def _sse(obj) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False, default=str)}\n\n"


@app.get("/api/frames/{image_id}/replay")
def replay(image_id: str, speed: float = 6.0):
    """Stream a stored run with its original pacing divided by `speed` (gaps capped for demos)."""
    a = cached(image_id)
    if not a:
        raise HTTPException(404, "bu kare henüz değerlendirilmedi")

    def gen():
        yield _sse(dict(kind="start", mode="replay", speed=speed))
        prev = a["trace"][0]["t"] if a["trace"] else time.time()
        for ev in a["trace"]:
            time.sleep(min(max(ev["t"] - prev, 0) / speed, 2.5))
            prev = ev["t"]
            yield _sse(ev)
        yield _sse(dict(kind="done", usage=a["usage"]))
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/frames/{image_id}/run")
def run(image_id: str, effort: str = "high"):
    """Run the agent live and stream every trace event as it happens."""
    scene(image_id)
    if not llm_client.available():
        raise HTTPException(503, "GLM_API_KEY tanımlı değil")
    with _lock:
        if image_id in _running:
            raise HTTPException(409, "bu kare için ajan zaten çalışıyor")
        _running.add(image_id)
    q: queue.Queue = queue.Queue()

    def work():
        try:
            out = assess(image_id, cb=q.put, effort=effort, use_cache=False)
            q.put(dict(kind="done", usage=out["usage"]))
        except Exception as ex:
            q.put(dict(kind="error", title=type(ex).__name__, detail=str(ex)))
        finally:
            _running.discard(image_id)
            q.put(None)

    threading.Thread(target=work, daemon=True).start()

    def gen():
        yield _sse(dict(kind="start", mode="live"))
        while True:
            try:
                ev = q.get(timeout=15)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            if ev is None:
                break
            yield _sse(ev)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


class ChatIn(BaseModel):
    question: str
    history: list[dict] = []


@app.post("/api/frames/{image_id}/chat")
def chat(image_id: str, body: ChatIn):
    a = cached(image_id)
    if not a:
        raise HTTPException(404, "önce kareyi değerlendirin")
    text, used = answer(body.question, a, body.history)
    return dict(answer=text, tools=used)


# ---------------------------------------------------------------- built web UI (demo: one process)
from pathlib import Path  # noqa: E402

from fastapi.staticfiles import StaticFiles  # noqa: E402

_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if _DIST.exists():
    @app.middleware("http")
    async def _no_cache_html(request, call_next):
        # hashed assets can be cached forever; the HTML that points at them must not be,
        # otherwise a rebuilt UI keeps loading the old bundle
        resp = await call_next(request)
        if not request.url.path.startswith(("/assets/", "/api/")):
            resp.headers["Cache-Control"] = "no-cache"
        return resp

    app.mount("/", StaticFiles(directory=_DIST, html=True), name="web")
