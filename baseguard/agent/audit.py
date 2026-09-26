"""Grounding audit of a submitted assessment.

Checks that what the agent *wrote* is backed by what its tools *returned* in this run. It never
judges the decisions themselves (which vehicle matters is the agent's call); it only catches
statements that contradict or are missing from the measurements, so the agent can fix them.
"""
from __future__ import annotations

import re

from core.scene import Scene

ID_RE = re.compile(r"\b(D\d{1,2}|T\d{4}|R\d{3})\b")
NUM_RE = re.compile(r"(?<![\d:])(\d+(?:[.,]\d+)?)\s*(km|m/s|m\b|dk\b|dakika|°)")
TOGETHER_RE = re.compile(r"konvoy|birlikte (?:hareket|seyr|ilerl|geliyor|gid)|grup halinde (?:hareket|ilerl)", re.I)
TOOL_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
NEGATION_RE = re.compile(r"(konvoy|birlikte)\w*\s+(?:\S+\s+){0,3}?(değil|yok|görülmüyor|desteklenmiyor|bulunmuyor)"
                         r"|(?:değil|yok)\w*\s+(?:\S+\s+){0,2}?konvoy|konvoy iddia", re.I)


def _texts(sub: dict) -> list[tuple[str, str]]:
    """(where, text) pairs of everything the agent wrote."""
    out = [("headline", sub.get("headline", "")), ("brief", sub.get("brief", ""))]
    for vid, v in (sub.get("vehicles") or {}).items():
        out.append((vid, " ".join([v.get("reason", "")] + list(v.get("evidence") or []))))
    for rid, r in (sub.get("reports") or {}).items():
        out.append((rid, " ".join([r.get("reason", "")] + [f"{c.get('claim', '')} {c.get('finding', '')}"
                                                          for c in r.get("claims_checked") or []])))
    return out


def _supported(x: float, unit: str, values: list[float]) -> bool:
    if unit == "km":
        return any(abs(v - x * 1000) <= max(60, 0.03 * x * 1000) or abs(v - x) <= 0.05 for v in values)
    if unit == "m":
        return any(abs(v - x) <= max(3, 0.02 * x) for v in values)
    if unit == "m/s":
        return any(abs(v - x) <= 0.15 for v in values)
    if unit in ("dk", "dakika"):
        return any(abs(v - x) <= 1.0 for v in values)
    return any(abs(v - x) <= 2 for v in values)  # degrees


def audit(sub: dict, scene: Scene, tool_texts: list[str]) -> list[str]:
    issues: list[str] = []
    required_v, optional_v = scene.subjects()
    coord_reports = [r["rid"] for r in scene.reports()["reports"] if r["scope"] == "koordinat"]
    vehicles, reports = sub.get("vehicles") or {}, sub.get("reports") or {}

    # 1. coverage
    miss_v = [v for v in required_v if v not in vehicles]
    if miss_v:
        issues.append(f"karar verilmeyen araçlar: {', '.join(miss_v)}")
    miss_r = [r for r in coord_reports if r not in reports]
    if miss_r:
        issues.append(f"değerlendirilmeyen koordinatlı raporlar: {', '.join(miss_r)}")

    # 2. ids that do not exist in this frame / this run's tool output
    seen = " ".join(tool_texts)
    known = set(required_v + optional_v + list(reports) + ID_RE.findall(seen))
    for where, text in _texts(sub):
        unknown = sorted({i for i in ID_RE.findall(text) if i not in known})
        if unknown:
            issues.append(f"{where}: araç çıktılarında geçmeyen kimlik(ler): {', '.join(unknown)}")

    # 3. "moving together / convoy" must be backed by get_motion.moving_together_with
    track_of = {r["detection"]: r["track_id"] for r in scene.track_matches()["matches"]}
    for where, text in _texts(sub):
        # report assessments quote the report's own convoy claim; negated mentions are not claims
        if where in reports or not TOGETHER_RE.search(text) or NEGATION_RE.search(text):
            continue
        ids = [where] if where in vehicles else [i for i in ID_RE.findall(text) if not i.startswith("R")]
        if not ids:  # "convoy" without naming vehicles: check every track in the frame
            ids = [m["track_id"] for m in scene.track_matches()["matches"] if m["track_id"]]
        tids = [track_of.get(i) or (i if i.startswith("T") else None) for i in ids]
        tids = [t for t in tids if t]
        if tids and not any(scene.motion(t)["moving_together_with"] for t in tids):
            issues.append(f"{where}: 'konvoy/birlikte hareket' deniyor ama {', '.join(tids)} için "
                          "get_motion.moving_together_with boş (son 1 saatte ortalama ≤500 m yakın seyreden kayıt yok)")

    # 4. numbers with units must appear (within rounding) in some tool output of this run
    # tools report signed values (sweep -549°, closing -0.64 m/s); prose states magnitude + direction
    values = [abs(float(v)) for v in TOOL_NUM_RE.findall(seen)]
    for where, text in _texts(sub):
        bad = []
        for num, unit in NUM_RE.findall(text):
            x = float(num.replace(",", "."))
            if not _supported(x, unit, values):
                bad.append(f"{num} {unit}")
        if bad:
            issues.append(f"{where}: araç çıktılarında karşılığı olmayan sayı(lar): {', '.join(dict.fromkeys(bad))} "
                          "(sayıları araç çıktısından aynen kullan, kendin hesaplama)")
    return issues
