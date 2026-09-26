"""Detection <-> track matching and motion measurements. Measurements only: no interpretation."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment

from . import config
from .data import ImageMeta, TrackPoint, base, tracks
from .geo import LatLon, angle_diff, bearing, compass, haversine

STOP_STEP_M = 25.0  # < this in 5 min = standing still (observed position noise is ~0-10 m)


# ---------------------------------------------------------------- matching

@dataclass
class Match:
    det_idx: int
    track_id: str
    dist_m: float
    runner_up: tuple[str, float] | None  # second-closest track at capture time


def tracks_at(t: str) -> dict[str, TrackPoint]:
    """Tracks whose history ends at time t (every track ends at an image's capture moment)."""
    return {tid: pts[-1] for tid, pts in tracks().items() if pts[-1].time == t}


def _assign(det_pos, det_idx, cands, tids, gate) -> list[Match]:
    if not det_idx or not tids:
        return []
    D = np.array([[haversine(det_pos[i], cands[t].pos) for t in tids] for i in det_idx])
    rows, cols = linear_sum_assignment(np.where(D <= gate, D, 1e6))
    out = []
    for r, c in zip(rows, cols):
        if D[r, c] <= gate:
            order = np.argsort(D[r])
            ru = next(((tids[j], round(float(D[r, j]), 1)) for j in order if j != c), None)
            out.append(Match(det_idx[r], tids[c], round(float(D[r, c]), 1), ru))
    return out


def match(img: ImageMeta, det_pos: list[LatLon], det_conf: list[float],
          gate_m: float | None = None) -> tuple[list[Match], list[str], list[str]]:
    """One-to-one assignment of detections to tracks ending at capture time (Hungarian, distance-gated).

    Confident boxes are assigned first, then weak ones against the leftover tracks, so a weak
    duplicate box cannot take a track from a confident one.
    Returns (matches, unmatched track ids ending inside the frame, track ids ending outside the frame).
    """
    fp = img.footprint
    cands = tracks_at(img.time)
    gate = gate_m or max(config.MATCH_GATE_MIN_M, config.MATCH_GATE_PX * fp.m_per_px)

    hi = [i for i, c in enumerate(det_conf) if c >= config.DET_MIN_CONF]
    lo = [i for i, c in enumerate(det_conf) if c < config.DET_MIN_CONF]
    matches = _assign(det_pos, hi, cands, list(cands), gate)
    left = [t for t in cands if t not in {m.track_id for m in matches}]
    matches += _assign(det_pos, lo, cands, left, gate)

    matched_t = {m.track_id for m in matches}
    inside = [t for t in cands if t not in matched_t and fp.contains(cands[t].pos, margin_m=2.0)]
    outside = [t for t in cands if t not in matched_t and not fp.contains(cands[t].pos, margin_m=2.0)]
    return matches, inside, outside


# ---------------------------------------------------------------- motion

@dataclass
class Stop:
    start: str
    end: str
    minutes: int
    dist_to_base_m: float


@dataclass
class Motion:
    track_id: str
    start: str
    end: str
    dist_to_base_series: list[tuple[str, int]]   # every 15 min, oldest first
    dist_to_base_now_m: float
    start_dist_to_base_m: float
    min_dist_to_base_m: float
    min_dist_time: str
    speed_last_10m_ms: float
    speed_last_30m_ms: float
    moving_speed_ms: float          # mean speed over steps where it moved
    path_len_m: float
    net_disp_m: float
    closing_rate_30m_ms: float      # + = distance to base shrinking
    closing_rate_60m_ms: float
    heading_deg: float | None       # direction of the most recent movement
    heading_compass: str | None
    bearing_to_base_deg: float
    heading_vs_base_deg: float | None  # 0 = pointing straight at the base
    base_sweep_deg: float           # signed angle swept around the base over 2 h
    eta_to_base_min: float | None   # distance / 30-min closing rate, when closing
    moving_now: bool
    stopped_minutes_total: int
    stops: list[Stop] = field(default_factory=list)
    polyline: list[tuple[str, float, float]] = field(default_factory=list)


def _path(pts: list[TrackPoint]) -> float:
    return sum(haversine(a.pos, c.pos) for a, c in zip(pts, pts[1:]))


def _since(pts: list[TrackPoint], minutes: int) -> list[TrackPoint]:
    t0 = pts[-1].tmin - minutes
    return [p for p in pts if p.tmin >= t0]


def _at(pts: list[TrackPoint], minutes_ago: int) -> TrackPoint:
    target = pts[-1].tmin - minutes_ago
    return min(pts, key=lambda q: abs(q.tmin - target))


def analyze(track_id: str) -> Motion:
    pts = tracks()[track_id]
    b = base()
    now = pts[-1]
    steps = [haversine(a.pos, c.pos) for a, c in zip(pts, pts[1:])]
    dts = [(c.tmin - a.tmin) * 60 for a, c in zip(pts, pts[1:])]

    stops: list[Stop] = []
    i = 0
    while i < len(steps):
        if steps[i] < STOP_STEP_M:
            j = i
            while j + 1 < len(steps) and steps[j + 1] < STOP_STEP_M:
                j += 1
            s, e = pts[i], pts[j + 1]
            if e.tmin - s.tmin >= 10:
                stops.append(Stop(s.time, e.time, e.tmin - s.tmin, round(haversine(s.pos, b))))
            i = j + 1
        else:
            i += 1

    moving = [(s, dt) for s, dt in zip(steps, dts) if s >= STOP_STEP_M]
    moving_speed = sum(s for s, _ in moving) / max(1, sum(dt for _, dt in moving)) if moving else 0.0

    def speed(minutes):
        seg = _since(pts, minutes)
        dt = (seg[-1].tmin - seg[0].tmin) * 60
        return _path(seg) / dt if dt else 0.0

    dists = [haversine(p.pos, b) for p in pts]
    d_now = dists[-1]
    d30, d60 = (haversine(_at(pts, m).pos, b) for m in (30, 60))
    close30 = (d30 - d_now) / 1800

    heading = None
    for p in reversed(pts[:-1]):
        if haversine(p.pos, now.pos) >= STOP_STEP_M * 2:
            heading = bearing(p.pos, now.pos)
            break
    b_to_base = bearing(now.pos, b)
    brs = [bearing(b, p.pos) for p in pts]
    imin = int(np.argmin(dists))

    return Motion(
        track_id=track_id, start=pts[0].time, end=now.time,
        dist_to_base_series=[(p.time, round(d)) for p, d in zip(pts, dists) if (now.tmin - p.tmin) % 15 == 0],
        dist_to_base_now_m=round(d_now), start_dist_to_base_m=round(dists[0]),
        min_dist_to_base_m=round(dists[imin]), min_dist_time=pts[imin].time,
        speed_last_10m_ms=round(speed(10), 1), speed_last_30m_ms=round(speed(30), 1),
        moving_speed_ms=round(moving_speed, 1), path_len_m=round(_path(pts)),
        net_disp_m=round(haversine(pts[0].pos, now.pos)),
        closing_rate_30m_ms=round(close30, 2), closing_rate_60m_ms=round((d60 - d_now) / 3600, 2),
        heading_deg=None if heading is None else round(heading),
        heading_compass=None if heading is None else compass(heading),
        bearing_to_base_deg=round(b_to_base),
        heading_vs_base_deg=None if heading is None else round(angle_diff(heading, b_to_base)),
        base_sweep_deg=round(sum((c - a + 540) % 360 - 180 for a, c in zip(brs, brs[1:]))),
        eta_to_base_min=round(d_now / close30 / 60, 1) if close30 > 0.3 else None,
        moving_now=steps[-1] >= STOP_STEP_M, stopped_minutes_total=sum(s.minutes for s in stops),
        stops=stops, polyline=[(p.time, p.lat, p.lon) for p in pts],
    )


def companions(track_id: str, window_min: int = 60, max_mean_sep_m: float = 500.0) -> list[dict]:
    """Other tracks ending at the same time whose mean separation from this one over the last
    `window_min` minutes was below `max_mean_sep_m`. Pure measurement; closest first."""
    me = tracks()[track_id]
    mine = {p.time: p.pos for p in me}
    out = []
    for tid, pts in tracks().items():
        if tid == track_id or pts[-1].time != me[-1].time:
            continue
        theirs = {p.time: p.pos for p in pts}
        common = sorted(set(mine) & set(theirs))[-(window_min // 5 + 1):]
        if len(common) < window_min // 5:
            continue
        seps = [haversine(mine[t], theirs[t]) for t in common]
        mean = sum(seps) / len(seps)
        if mean <= max_mean_sep_m:
            out.append(dict(track_id=tid, mean_sep_m=round(mean), max_sep_m=round(max(seps)),
                            both_moved_m=round(min(haversine(mine[common[0]], mine[common[-1]]),
                                                   haversine(theirs[common[0]], theirs[common[-1]])))))
    return sorted(out, key=lambda d: d["mean_sep_m"])


def describe(m: Motion) -> str:
    """One-line numeric summary for trace/UI."""
    km = lambda x: f"{x / 1000:.1f} km"
    parts = [f"üsse {km(m.start_dist_to_base_m)} ({m.start}) → {km(m.dist_to_base_now_m)} ({m.end})",
             f"en yakın {km(m.min_dist_to_base_m)} ({m.min_dist_time})",
             f"son 10 dk {m.speed_last_10m_ms} m/s", f"üs etrafında {m.base_sweep_deg:+d}°"]
    if m.stops:
        parts.append("duraklamalar: " + ", ".join(f"{s.start} ({s.minutes} dk)" for s in m.stops))
    return " · ".join(parts)
