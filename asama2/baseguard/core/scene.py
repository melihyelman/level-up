"""Per-image measurements, exposed step by step (each method backs one agent tool).

Everything returned here is a measurement or a lookup, never a judgement: which vehicle matters,
whether a report is true and how risky the scene is are decided by the agent.
"""
from __future__ import annotations

from dataclasses import asdict
from functools import cached_property
from pathlib import Path

from . import config
from .data import base, images, nearest_zone, tracks, zones
from .detect import clean, get_detections, load_cache, FAST_CACHE
from .geo import bearing, compass, haversine
from .reports import HEAVY, claims, relevant
from .tracks import analyze, companions, match


class Scene:
    def __init__(self, image_id: str, image_path: Path | None = None):
        if image_id not in images():
            raise KeyError(f"{image_id} image_meta.json içinde yok")
        self.id = image_id
        self.meta = images()[image_id]
        self.fp = self.meta.footprint
        self.image_path = image_path or config.IMAGES_DIR / f"{image_id}.jpg"

    # ------------------------------------------------------------ 1. image
    def info(self) -> dict:
        fp, b = self.fp, base()
        c = fp.center
        z, zd = nearest_zone(c)
        return dict(
            image_id=self.id, capture_time=self.meta.time, width_px=self.meta.width, height_px=self.meta.height,
            corners=dict(top_left=fp.tl, top_right=fp.tr, bottom_left=fp.bl, bottom_right=fp.br),
            center=[round(c[0], 6), round(c[1], 6)], footprint_m=[round(fp.width_m), round(fp.height_m)],
            m_per_px=round(fp.m_per_px, 3), nearest_zone=z.name, zone_dist_m=round(zd),
            base=dict(name=zones()[1], lat=b[0], lon=b[1]),
            dist_to_base_m=round(haversine(c, b)), direction_from_base=compass(bearing(b, c)),
        )

    # ------------------------------------------------------------ 2+3. detection + geolocation
    @cached_property
    def _dets(self):
        _, source = get_detections(self.id, self.image_path)
        raw = load_cache().get(self.id) or load_cache(FAST_CACHE).get(self.id, [])
        dets = sorted(clean(raw, min_conf=config.DET_CACHE_MIN_CONF), key=lambda d: -d.conf)
        return dets, source

    def detections(self, min_conf: float = config.DET_CACHE_MIN_CONF) -> dict:
        dets, source = self._dets
        b = base()
        out = []
        for i, d in enumerate(dets, 1):
            if d.conf < min_conf:
                continue
            lat, lon = self.fp.to_geo(*d.center)
            out.append(dict(id=f"D{i}", cls=d.cls, conf=d.conf, box_xywh=[d.x, d.y, d.w, d.h],
                            center_px=[round(v) for v in d.center], lat=round(lat, 6), lon=round(lon, 6),
                            dist_to_base_m=round(haversine((lat, lon), b))))
        return dict(model=source, min_conf=min_conf, count=len(out), detections=out)

    def detection(self, did: str) -> dict | None:
        return next((d for d in self.detections()["detections"] if d["id"] == did), None)

    # ------------------------------------------------------------ 4. track matching
    @cached_property
    def _match(self):
        dets = self.detections()["detections"]
        pos = [(d["lat"], d["lon"]) for d in dets]
        return dets, *match(self.meta, pos, [d["conf"] for d in dets])

    def track_matches(self) -> dict:
        dets, matches, inside, outside = self._match
        by = {m.det_idx: m for m in matches}
        rows = []
        for i, d in enumerate(dets):
            m = by.get(i)
            rows.append(dict(detection=d["id"], cls=d["cls"], conf=d["conf"],
                             track_id=m.track_id if m else None, dist_m=m.dist_m if m else None,
                             second_nearest=dict(track_id=m.runner_up[0], dist_m=m.runner_up[1]) if m and m.runner_up else None))
        track_only = []
        for tid in inside:
            p = tracks()[tid][-1].pos
            x, y = self.fp.to_px(p)
            near = min(dets, key=lambda d: haversine(p, (d["lat"], d["lon"])), default=None)
            track_only.append(dict(track_id=tid, center_px=[round(x), round(y)], lat=round(p[0], 6), lon=round(p[1], 6),
                                   nearest_detection=near["id"] if near else None,
                                   nearest_detection_dist_m=round(haversine(p, (near["lat"], near["lon"])), 1) if near else None))
        left = []
        for tid in outside:
            p = tracks()[tid][-1].pos
            dd = self.fp.dist_outside(p)
            if dd <= 500:
                left.append(dict(track_id=tid, dist_outside_frame_m=round(dd)))
        return dict(capture_time=self.meta.time, tracks_ending_at_capture=len(matches) + len(inside) + len(outside),
                    gate_m=round(max(config.MATCH_GATE_MIN_M, config.MATCH_GATE_PX * self.fp.m_per_px), 1),
                    matches=rows, tracks_in_frame_without_detection=track_only,
                    tracks_just_outside_frame=left)

    def subjects(self) -> tuple[list[str], list[str]]:
        """Ids a complete assessment must decide on (confident boxes, weak boxes confirmed by a track,
        track-only vehicles), and ids it may decide on (weak boxes without a track)."""
        tm = {r["detection"]: r["track_id"] for r in self.track_matches()["matches"]}
        required, optional = [], []
        for d in self.detections()["detections"]:
            (required if d["conf"] >= config.DET_MIN_CONF or tm.get(d["id"]) else optional).append(d["id"])
        required += [t["track_id"] for t in self.track_matches()["tracks_in_frame_without_detection"]]
        return required, optional

    def track_of(self, did: str) -> str | None:
        return next((r["track_id"] for r in self.track_matches()["matches"] if r["detection"] == did), None)

    # ------------------------------------------------------------ 5. motion
    @staticmethod
    def motion(track_id: str, with_polyline: bool = False) -> dict:
        m = analyze(track_id)
        d = asdict(m)
        d["stops"] = [asdict(s) for s in m.stops]
        if not with_polyline:
            d.pop("polyline")
        d["moving_together_with"] = companions(track_id)
        return d

    # ------------------------------------------------------------ 6. reports
    def _claim_table(self, report, near: list[dict], dets: list[dict]) -> list[dict]:
        """Each parsed claim next to the measurements it can be compared with. No verdicts."""
        c = claims(report)
        rows = []
        want = (HEAVY if c.vtype == "heavy" else {c.vtype}) if c.vtype else None
        label = "/".join(sorted(want)) if want else None

        def desc(n):
            if n["cls"].startswith("("):
                return f"{n['id']} (sınıf yok, yalnız kayıt) {n['dist_m']} m"
            return f"{n['id']} {n['cls']} {n['conf']:.2f} {n['dist_m']} m"

        if want:
            same_near = [n for n in near if n["cls"] in want]
            in_frame = [d for d in dets if d["cls"] in want]
            strong = [d for d in in_frame if d["conf"] >= config.DET_MIN_CONF]
            rows.append(dict(claim=f"tip: {label}", measurement=(
                f"noktanın 60 m içinde {label}: {len(same_near)} ({', '.join(desc(n) for n in same_near) or '—'}); "
                f"60 m içindeki tüm araçlar: {', '.join(desc(n) for n in near) or 'yok'}; "
                f"karede {label}: güvenli (≥{config.DET_MIN_CONF}) {len(strong)}, zayıf {len(in_frame) - len(strong)} "
                f"({', '.join(d['id'] + ' ' + format(d['conf'], '.2f') for d in in_frame) or '—'})")))
        if c.count is not None:
            sel = [d for d in dets if not want or d["cls"] in want]
            rows.append(dict(claim=f"sayı: {c.count}" + (f" {label}" if label else ""), measurement=(
                f"noktanın 60 m içinde {label or 'araç'}: {len([n for n in near if not want or n['cls'] in want])}; "
                f"karede {label or 'araç'}: güvenli {sum(d['conf'] >= config.DET_MIN_CONF for d in sel)}, "
                f"zayıf {sum(d['conf'] < config.DET_MIN_CONF for d in sel)}")))
        if c.baseline_count is not None:
            rows.append(dict(claim=f"yoğunluk: olağan ~{c.baseline_count}, rapor {'olağandan yoğun' if c.busier_than_usual else 'olağan'} diyor",
                             measurement=f"karede {len(dets)} tespit, noktanın 60 m içinde {len(near)} araç"))
        if c.stationary or c.moving:
            states = []
            for n in near:
                if not n["track_id"]:
                    states.append(f"{n['id']}: hareket kaydı yok")
                    continue
                m = self.motion(n["track_id"])
                states.append(f"{n['id']}/{n['track_id']}: son 30 dk {m['speed_last_30m_ms']} m/s, şu an "
                              f"{'hareketli' if m['moving_now'] else 'duruyor'}, 30 dk yaklaşma {m['closing_rate_30m_ms']} m/s")
            kind = "duruyor" if c.stationary else ("üsse yaklaşıyor" if c.approaching else "uzaklaşıyor" if c.leaving else "hareket halinde")
            rows.append(dict(claim=f"hareket: {kind}", measurement="; ".join(states) or "noktanın 60 m içinde araç yok"))
        if c.identity:
            rows.append(dict(claim="kimlik: dost/planlı/teyitli unsur",
                             measurement="görüntü ve hareket verisi kimliği doğrulayamaz; yalnızca tip ve hareket tutarlılığı karşılaştırılabilir"))
        if c.color or c.cargo:
            first = next((n["id"] for n in near), None)
            rows.append(dict(claim="görünüş: " + ", ".join(x for x in [c.color, "yük/örtü" if c.cargo else None] if x),
                             measurement=f"tespit modeli renk/yük vermez; view_region ile bakılabilir (en yakın: {first or '—'})"))
        return rows


    def reports(self, radius_m: float = config.REPORT_RADIUS_M, lookback_min: int = config.REPORT_LOOKBACK_MIN,
                include_general: bool = False) -> dict:
        dets = self.detections()["detections"]
        tm = {r["detection"]: r["track_id"] for r in self.track_matches()["matches"]}
        track_only = self.track_matches()["tracks_in_frame_without_detection"]
        out = []
        for rr in relevant(self.meta, radius_m, lookback_min, include_general):
            item = dict(rid=rr.report.rid, time=rr.report.time, source=rr.report.source, text=rr.report.text,
                        scope=rr.scope, minutes_before_capture=rr.age_min)
            if rr.scope == "koordinat":
                item.update(point=list(rr.loc.coord), point_decimals=rr.loc.coord_decimals,
                            point_px=list(rr.px), dist_point_to_frame_m=rr.dist_to_frame_m)
                if rr.dist_to_frame_m == 0:
                    near = []
                    for d in dets:
                        dist = haversine(rr.loc.coord, (d["lat"], d["lon"]))
                        if dist <= 60:
                            near.append(dict(id=d["id"], cls=d["cls"], conf=d["conf"], dist_m=round(dist),
                                             track_id=tm.get(d["id"])))
                    for t in track_only:
                        dist = haversine(rr.loc.coord, (t["lat"], t["lon"]))
                        if dist <= 60:
                            near.append(dict(id=t["track_id"], cls="(tespit yok, yalnız hareket kaydı)", conf=None,
                                             dist_m=round(dist), track_id=t["track_id"]))
                    item["within_60m_of_point"] = sorted(near, key=lambda x: x["dist_m"])
                    item["claims_vs_measurements"] = self._claim_table(rr.report, item["within_60m_of_point"], dets)
            else:
                item["zone"] = rr.loc.zone
            out.append(item)
        counts = {}
        for d in dets:
            counts.setdefault(d["cls"], {"conf>=0.3": 0, "conf<0.3": 0})
            counts[d["cls"]]["conf>=0.3" if d["conf"] >= 0.3 else "conf<0.3"] += 1
        return dict(capture_time=self.meta.time, window=f"çekimden {lookback_min} dk önce – 30 dk sonra",
                    radius_m=radius_m, frame_detection_counts=counts, reports=out)
