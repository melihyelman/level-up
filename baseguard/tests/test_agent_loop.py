"""Agent loop with a scripted fake LLM: tool dispatch, images, schema check, grounding audit, caching."""
import json
from types import SimpleNamespace as NS

import pytest

from agent import llm_client, runner
from agent.audit import audit
from core import config
from core.scene import Scene

FRAME = "img_000860"


def _call(i, name, args):
    return NS(id=f"c{i}", type="function", function=NS(name=name, arguments=json.dumps(args, ensure_ascii=False)),
              model_dump=lambda: {"id": f"c{i}", "type": "function",
                                  "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}})


def _resp(*calls, content=""):
    return NS(choices=[NS(message=NS(content=content, tool_calls=list(calls) or None, reasoning_content="not: T0122 yaklaşıyor"))],
              usage=NS(prompt_tokens=100, completion_tokens=10, completion_tokens_details=None))


def _decision(action="işlem gerekmez", reason="olağan"):
    return {"action": action, "confidence": "yüksek", "reason": reason}


def _submission(vehicles):
    return {"action": "hemen teyit/müdahale", "headline": "Üsse yaklaşan kamyon",
            "brief": "D6/T0122 üsse 5958 m'den 1647 m'ye geldi.", "vehicles": vehicles,
            "reports": {"R125": {"verdict": "tespitle uyumlu", "reason": "tip uyumlu",
                                 "claims_checked": [{"claim": "tip: ağır araç", "finding": "D6 truck 3 m"}]},
                        "R119": {"verdict": "doğrulanamaz", "reason": "kimlik teyit edilemez", "claims_checked": []}}}


@pytest.fixture
def fake_llm(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "BRIEFS_DIR", tmp_path)
    monkeypatch.setattr(llm_client, "available", lambda: True)
    all_v = {v: _decision() for v in Scene(FRAME).subjects()[0]}
    all_v["D6"] = _decision("hemen teyit/müdahale", "T0122 üsse 1647 m, yaklaşıyor")
    missing_d2 = {k: v for k, v in all_v.items() if k != "D2"}
    script = iter([
        _resp(_call(1, "get_image_info", {}), _call(2, "detect_vehicles", {})),
        _resp(_call(3, "match_tracks", {})),
        _resp(_call(4, "get_motion", {"track_ids": ["T0122", "T0092"]}), _call(5, "get_reports", {})),
        _resp(_call(6, "submit_assessment", {**_submission(all_v), "action": "YANLIŞ"})),   # schema error
        _resp(_call(7, "submit_assessment", _submission(missing_d2))),                      # audit: D2 missing
        _resp(_call(8, "submit_assessment", _submission(all_v))),                           # accepted
    ])
    sent, efforts = [], []

    def chat(messages, usage, tools=None, effort="high", **kw):
        sent.append(json.loads(json.dumps(messages, default=str)))
        efforts.append(effort)
        r = next(script)
        usage.add(r.usage, 0.0)
        return r

    monkeypatch.setattr(llm_client, "chat", chat)
    return NS(sent=sent, efforts=efforts)


def test_loop_tools_schema_audit_and_cache(fake_llm):
    events = []
    out = runner.assess(FRAME, cb=events.append, use_cache=False)
    b = out["brief"]
    assert b["action"] == "hemen teyit/müdahale" and b["audit"] == []
    assert b["vehicles"][0]["id"] == "D6" and b["vehicles"][0]["track_id"] == "T0122"   # most urgent first
    assert {r["rid"] for r in b["reports"]} == {"R125", "R119"}
    called = [e["title"] for e in events if e["kind"] == "tool_call"]
    assert called == ["get_image_info", "detect_vehicles", "match_tracks", "get_motion", "get_reports"]
    assert any(e["kind"] == "warn" for e in events)                                   # schema error bounced
    audits = [e for e in events if e["kind"] == "audit"]
    assert "D2" in audits[0]["detail"][0] and audits[-1]["detail"] == []             # audit bounced, then passed
    assert out["audit_rounds"] == 1
    assert runner.cached(FRAME)["brief"]["headline"] == "Üsse yaklaşan kamyon"
    assert runner.actions_by_id(b)["T0122"] == "hemen teyit/müdahale"


def test_inputs_to_the_model(fake_llm):
    runner.assess(FRAME, use_cache=False)
    first_user = fake_llm.sent[0][1]["content"]
    assert any(c.get("type") == "image_url" for c in first_user)                      # raw frame up front
    assert any(isinstance(m.get("content"), list) and any(c.get("type") == "image_url" for c in m["content"])
               for m in fake_llm.sent[1][2:])                                          # annotated frame after detect
    assert set(fake_llm.efforts) == {"high"}
    assistant = next(m for m in fake_llm.sent[1] if m["role"] == "assistant")
    assert "[Bu turdaki düşünce notlarım]" in assistant["content"]                    # reasoning carried over
    tools = next(m for m in fake_llm.sent[2] if m["role"] == "tool")                  # measurements only
    assert "level" not in tools["content"] and "verdict" not in tools["content"]


# ---------------------------------------------------------------- audit unit tests

def _tool_texts(frame, *tracks):
    s = Scene(frame)
    return [json.dumps(x, ensure_ascii=False, default=list) for x in
            [s.info(), s.detections(), s.track_matches(), s.reports()] + [s.motion(t) for t in tracks]]


def test_audit_catches_the_reviewed_mistakes():
    # img_005788, reviewed by hand: D4 skipped and an unsupported "convoy"
    s = Scene("img_005788")
    vehicles = {v: _decision() for v in s.subjects()[0] if v != "D4"}
    vehicles["D2"] = _decision("izlemeye al", "konvoyun parçası, üsse yaklaşıyor")
    sub = {"action": "izlemeye al", "headline": "h", "brief": "b", "vehicles": vehicles,
           "reports": {"R017": {"verdict": "tespitle çelişiyor", "claims_checked": [], "reason": "r"},
                       "R032": {"verdict": "kısmen uyumlu", "claims_checked": [], "reason": "r"}}}
    issues = audit(sub, s, _tool_texts("img_005788", "T0112"))
    assert any("D4" in i and "karar verilmeyen" in i for i in issues)
    assert any(i.startswith("D2:") and "moving_together_with" in i for i in issues)


def test_audit_numbers_and_ids():
    s = Scene(FRAME)
    vehicles = {v: _decision() for v in s.subjects()[0]}
    vehicles["D6"] = _decision("hemen teyit/müdahale", "T0122 1.6 km uzakta, son 10 dk 6.2 m/s, ~13 dk")
    ok = {"action": "izlemeye al", "headline": "h", "brief": "b", "vehicles": vehicles,
          "reports": {"R125": {"verdict": "tespitle uyumlu", "claims_checked": [], "reason": "r"},
                      "R119": {"verdict": "doğrulanamaz", "claims_checked": [], "reason": "r"}}}
    texts = _tool_texts(FRAME, "T0122")
    assert audit(ok, s, texts) == []                                                 # rounding tolerated
    bad = json.loads(json.dumps(ok))
    bad["vehicles"]["D6"]["reason"] = "T0122 3.9 km yaklaştı; T9999 ile birlikte"     # invented number + id
    issues = audit(bad, s, texts)
    assert any("3.9 km" in i for i in issues) and any("T9999" in i for i in issues)


def test_schema_check():
    assert runner._valid({"action": "izlemeye al", "headline": "h", "brief": "b",
                          "vehicles": {"D1": {"action": "izlemeye al", "confidence": "düşük", "reason": "r"}}}) is None
    assert runner._valid({"action": "izlemeye al", "headline": "h", "brief": "b",
                          "vehicles": [{"id": "D1"}]})                               # list instead of keyed object
    assert runner._valid({"action": "izlemeye al", "headline": "h", "brief": "b",
                          "vehicles": {"D1": {"action": "izlemeye al", "reason": "r"}}})  # no confidence


def test_tidy_and_lenient_zone_reports():
    sub = runner._tidy({"action": "izlemeye al", "headline": "h", "brief": "b",
                        "vehicles": {"D1": _decision()},
                        "reports": {"R017": {"verdict": "tespitle çelişiyor", "claims_checked": [], "reason": "r"},
                                    "R110": {"verdict": "doğrulanamaz", "reason": "bölge raporu"},
                                    "verdict": "ilgisiz"}})
    assert "verdict" not in sub["reports"]
    assert runner._valid(sub, ["R017"]) is None             # zone report may omit claims_checked
    assert runner._valid(sub, ["R017", "R110"])             # a coordinate report may not


def test_audit_no_false_alarms_on_signs_and_quoted_convoys():
    s = Scene("img_000926")
    vehicles = {v: _decision() for v in s.subjects()[0]}
    vehicles["D1"] = _decision("izlemeye al", "T0172 üs etrafında 549° tur attı")          # tool: -549
    sub = {"action": "izlemeye al", "headline": "h", "brief": "Konvoy yok; araçlar ayrı ayrı hareket ediyor.",
           "vehicles": vehicles, "reports": {r["rid"]: {"verdict": "ilgisiz", "claims_checked": [], "reason": "r"}
                                             for r in s.reports()["reports"] if r["scope"] == "koordinat"}}
    assert audit(sub, s, _tool_texts("img_000926", "T0172")) == []
    s2 = Scene("img_001230")
    sub2 = {"action": "izlemeye al", "headline": "h", "brief": "b",
            "vehicles": {v: _decision() for v in s2.subjects()[0]},
            "reports": {"R086": {"verdict": "tespitle çelişiyor", "claims_checked": [],
                                 "reason": "raporun 3 araçlık kamyon konvoyu iddiası tutmuyor"}}}
    assert not any("konvoy" in i for i in audit(sub2, s2, _tool_texts("img_001230")))
