"""Agent loop: the LLM drives the tools step by step and makes the call.

Every tool call and result is emitted as a trace event (UI / CLI), so the demo shows what the agent
actually did. A submitted assessment is schema-checked and then grounding-audited against this run's
tool outputs; problems go back to the agent to fix. There is no rule-based fallback verdict: without
the LLM the product shows measurements only.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from stage2.asama2.baseguard.core import config
from stage2.asama2.baseguard.core.render import raw_frame, to_data_url
from stage2.asama2.baseguard.core.scene import Scene
from . import llm_client
from .audit import ID_RE, audit
from .prompts import NUDGE, SYSTEM, USER_TEMPLATE
from .tools import ACTIONS, CONFIDENCE, REPORT_VERDICTS, ToolBox, schemas

MAX_TURNS = 12               # tool rounds before we force a submit
MAX_AUDIT_ROUNDS = 2         # times the agent is asked to fix audit findings before we accept with warnings
MAX_PROMPT_TOKENS = 500_000  # per run, protects the shared budget from runaway loops
DEFAULT_EFFORT = "high"      # "low" skipped checks it had the data for (see review of img_005788)
NOTES_MAX_CHARS = 1500       # reasoning carried into the next turn, per turn

Emit = Callable[[dict], None]


def _emit(cb: Emit | None, kind: str, title: str, detail=None) -> dict:
    ev = dict(kind=kind, title=title, detail=detail, t=time.time())
    if cb:
        cb(ev)
    return ev


def _tidy(a: dict) -> dict:
    """Drop stray non-id keys the model sometimes adds inside the keyed objects (e.g. a loose "verdict")."""
    for k in ("vehicles", "reports"):
        if isinstance(a.get(k), dict):
            a[k] = {i: v for i, v in a[k].items() if ID_RE.fullmatch(i)}
    return a


def _valid(a: dict, coord_reports: list[str] | None = None) -> str | None:
    """Schema check (providers do not always enforce the JSON schema)."""
    if a.get("action") not in ACTIONS:
        return f"action şunlardan biri olmalı: {ACTIONS}"
    if not a.get("headline") or not a.get("brief"):
        return "headline ve brief zorunlu"
    if not isinstance(a.get("vehicles"), dict) or not a["vehicles"]:
        return "vehicles, araç kimliğine göre anahtarlanmış bir nesne olmalı: {\"D1\": {...}, \"T0223\": {...}}"
    bad = [k for k, v in a["vehicles"].items() if not isinstance(v, dict) or v.get("action") not in ACTIONS
           or v.get("confidence") not in CONFIDENCE or not v.get("reason")]
    if bad:
        return f"vehicles: her araçta action, confidence (yüksek/düşük) ve reason olmalı (sorunlu: {bad})"
    if not isinstance(a.get("reports", {}), dict):
        return "reports, rapor kimliğine göre anahtarlanmış bir nesne olmalı: {\"R017\": {...}}"
    coord = set(coord_reports or [])
    bad = [k for k, r in (a.get("reports") or {}).items() if not isinstance(r, dict)
           or r.get("verdict") not in REPORT_VERDICTS
           or (k in coord and not isinstance(r.get("claims_checked"), list))]
    if bad:
        return (f"reports: her raporda verdict ({'/'.join(REPORT_VERDICTS)}) olmalı; koordinatlı raporlarda "
                f"claims_checked listesi de zorunlu (sorunlu: {bad})")
    return None


def _with_notes(content: str | None, reasoning: str) -> str:
    """Reasoning is not sent back by the API on later turns, so findings noticed while thinking
    (e.g. a circling track) were lost before the final answer. Carry them as plain assistant text,
    which every OpenAI-compatible provider accepts."""
    content = (content or "").strip()
    if not reasoning.strip():
        return content
    notes = reasoning.strip()
    if len(notes) > NOTES_MAX_CHARS:
        notes = notes[:NOTES_MAX_CHARS] + " …"
    return (content + "\n\n" if content else "") + f"[Bu turdaki düşünce notlarım]\n{notes}"


def _normalise(sub: dict, scene: Scene, audit_issues: list[str]) -> dict:
    """Keyed submission -> brief with vehicle / report lists, most urgent first."""
    track_of = {r["detection"]: r["track_id"] for r in scene.track_matches()["matches"]}
    vehicles = [dict(id=vid, track_id=track_of.get(vid) or (vid if vid.startswith("T") else None), **v)
                for vid, v in sub["vehicles"].items()]
    vehicles.sort(key=lambda v: (ACTIONS.index(v["action"]), CONFIDENCE.index(v["confidence"])))
    reports = [dict(rid=rid, claims_checked=r.get("claims_checked") or [], **{k: v for k, v in r.items() if k != "claims_checked"})
               for rid, r in (sub.get("reports") or {}).items()]
    return dict(action=sub["action"], headline=sub["headline"], brief=sub["brief"], vehicles=vehicles,
                reports=reports, uncertainties=sub.get("uncertainties") or [], audit=audit_issues)


def cached(image_id: str, directory: Path | None = None) -> dict | None:
    f = (directory or config.BRIEFS_DIR) / f"{image_id}.json"
    return json.loads(f.read_text()) if f.exists() else None


def assess(image_id: str, cb: Emit | None = None, effort: str = DEFAULT_EFFORT, use_cache: bool = True,
           save_dir: Path | None = None) -> dict:
    """save_dir: where to store the run (default: the brief cache)."""
    if use_cache and (out := cached(image_id, save_dir)):
        for ev in out["trace"]:
            cb and cb(ev)
        return out
    if not llm_client.available():
        raise llm_client.LLMUnavailable("GLM_API_KEY tanımlı değil; ajan çalıştırılamaz")

    scene = Scene(image_id)
    tb = ToolBox(scene)
    usage = llm_client.Usage()
    trace: list[dict] = []
    tool_texts: list[str] = []
    task = USER_TEMPLATE.format(image_id=image_id)
    tool_schemas = schemas(scene)
    coord_reports = [r["rid"] for r in scene.reports()["reports"] if r["scope"] == "koordinat"]
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": [
                    {"type": "text", "text": task + "\nKarenin işaretsiz hali ektedir."},
                    {"type": "image_url", "image_url": {"url": to_data_url(raw_frame(scene))}}]}]
    trace.append(_emit(cb, "user", "Görev", task + " (+ işaretsiz kare)"))

    brief, nudged, audit_rounds, last_issues = None, False, 0, []
    for turn in range(MAX_TURNS + MAX_AUDIT_ROUNDS + 1):
        force = turn >= MAX_TURNS
        kw = {"tool_choice": {"type": "function", "function": {"name": "submit_assessment"}}} if force else {}
        resp = llm_client.chat(messages, usage, tools=tool_schemas, effort=effort, **kw)
        msg = resp.choices[0].message
        reasoning = getattr(msg, "reasoning_content", None) or ""
        if reasoning:
            trace.append(_emit(cb, "thought", "Düşünce", reasoning[:2000]))
        if msg.content and msg.content.strip():
            trace.append(_emit(cb, "say", "Ajan", msg.content.strip()[:1500]))
        if usage.prompt_tokens > MAX_PROMPT_TOKENS:
            raise RuntimeError("çalışma başına token sınırı aşıldı")

        if not msg.tool_calls:
            if nudged:
                raise RuntimeError("ajan submit_assessment çağırmadı")
            messages += [{"role": "assistant", "content": _with_notes(msg.content, reasoning)},
                         {"role": "user", "content": NUDGE}]
            nudged = True
            continue

        messages.append({"role": "assistant", "content": _with_notes(msg.content, reasoning),
                         "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
        shown = []
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if name == "submit_assessment":
                args = _tidy(args)
                if err := _valid(args, coord_reports):
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": f"Geçersiz: {err}. Düzeltip tekrar gönder."})
                    trace.append(_emit(cb, "warn", "Geçersiz değerlendirme", err))
                    continue
                issues = audit(args, scene, tool_texts)
                if issues and audit_rounds < MAX_AUDIT_ROUNDS:
                    audit_rounds += 1
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content":
                                     "Denetim tutarsızlık buldu; düzeltip submit_assessment'ı yeniden gönder:\n- "
                                     + "\n- ".join(issues)})
                    trace.append(_emit(cb, "audit", f"Denetim ({audit_rounds}. tur): düzeltme istendi", issues))
                    continue
                trace.append(_emit(cb, "audit", "Denetim: kalan uyarılarla kabul edildi" if issues else "Denetim: sorun yok", issues))
                last_issues = issues
                brief = _normalise(args, scene, issues)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": "alındı"})
                continue
            trace.append(_emit(cb, "tool_call", name, args))
            text, img = tb.call(name, args)
            tool_texts.append(text)
            trace.append(_emit(cb, "tool_result", name, text))
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": text})
            if img:
                shown += [{"type": "text", "text": f"{name} {args.get('target', '')} görüntüsü:"},
                          {"type": "image_url", "image_url": {"url": img}}]
        if brief:
            break
        if shown:
            messages.append({"role": "user", "content": shown})
    if not brief:
        raise RuntimeError("tur sınırında değerlendirme gelmedi")

    trace.append(_emit(cb, "final", "Değerlendirme", brief))
    out = dict(image_id=image_id, brief=brief, trace=trace, usage=usage.as_dict(), effort=effort,
               audit_rounds=audit_rounds, audit_warnings=len(last_issues),
               model=llm_client.MODEL, created=time.time())
    target = save_dir or config.BRIEFS_DIR
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{image_id}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    return out


def actions_by_id(brief: dict) -> dict:
    """D#/T#### -> action, for colouring the frame with the agent's decisions."""
    out = {}
    for v in brief.get("vehicles", []):
        out[v["id"]] = v["action"]
        if v.get("track_id"):
            out[v["track_id"]] = v["action"]
    return out
