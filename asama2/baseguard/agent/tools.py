"""Agent tools. Each returns measurements for the frame under assessment; the agent does the reasoning."""
from __future__ import annotations

import json

from stage2.asama2.baseguard.core import config
from stage2.asama2.baseguard.core.data import reports as all_reports, tracks
from stage2.asama2.baseguard.core.geo import haversine
from stage2.asama2.baseguard.core.render import annotate, crop, to_data_url
from stage2.asama2.baseguard.core.reports import locate
from stage2.asama2.baseguard.core.scene import Scene

ACTIONS = ["hemen teyit/müdahale", "izlemeye al", "işlem gerekmez"]   # most urgent first
CONFIDENCE = ["yüksek", "düşük"]
REPORT_VERDICTS = ["tespitle uyumlu", "kısmen uyumlu", "tespitle çelişiyor", "doğrulanamaz", "ilgisiz"]


def _fn(name, desc, props=None, required=None):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props or {}, "required": required or []}}}


SCHEMAS = [
    _fn("get_image_info",
        "Karenin boyutu, çekim saati, dört köşe koordinatı (WGS84), yerdeki kapsama alanı, en yakın bölge, "
        "üssün konumu ve karenin üsse uzaklığı."),
    _fn("detect_vehicles",
        "1. gün tespit modelini kareye uygular. Her tespit: kimlik (D#), sınıf (car/van/truck/bus), güven, kutu, "
        "merkez piksel ve merkezin enlem/boylamı (köşe koordinatlarından doğrusal orantıyla), üsse uzaklık. "
        "Düşük güvenli kutular da döner; hangisinin gerçek araç olduğuna sen karar verirsin. "
        "Kutuların çizildiği görüntü ayrıca gösterilir.",
        {"min_conf": {"type": "number", "description": "en düşük güven, varsayılan 0.05"}}),
    _fn("match_tracks",
        "tracks.csv'de çekim saatinde biten hareket kayıtlarını tespitlerle eşleştirir (birebir, en yakın; "
        "mesafe eşiği içinde). Her tespit için eşleşen kayıt ve mesafe, ikinci en yakın kayıt; karede biten ama "
        "tespiti olmayan kayıtlar; karenin hemen dışında biten kayıtlar."),
    _fn("get_motion",
        "Bir hareket kaydının (T####) 2 saatlik ölçümleri: 15 dakikalık aralıklarla üsse uzaklık, son 10/30 dk hız, "
        "hareket halindeyken ortalama hız, toplam yol, üsse yaklaşma hızı, şu anki yön ve üsse göre açısı, üs "
        "etrafında süpürülen açı, en yakın geçiş, duraklamalar, tahmini varış süresi, son 1 saatte yakın "
        "seyreden diğer kayıtlar. Birden çok kaydı tek çağrıda istemek için track_ids kullan.",
        {"track_id": {"type": "string"},
         "track_ids": {"type": "array", "items": {"type": "string"}, "description": "ör. [\"T0122\", \"T0092\"]"}}),
    _fn("get_reports",
        "Kareyle ilgili saha raporları (ham metin, kaynak, saat). Koordinatlı raporlar için noktanın kareye uzaklığı, "
        "piksel konumu, noktanın 60 m içindeki tespitler/kayıtlar ve claims_vs_measurements: raporun her iddiası "
        "(tip, sayı, hareket, kimlik, görünüş) yanında karşılaştırılabileceği ölçümler (hüküm içermez). Bölge adı "
        "geçen raporlar ve karedeki sınıf sayıları da döner. Raporlar doğrulanmamıştır.",
        {"radius_m": {"type": "number", "description": "kareye uzaklık sınırı, varsayılan 250"},
         "lookback_min": {"type": "integer", "description": "çekimden kaç dk öncesine kadar, varsayılan 180"},
         "include_general": {"type": "boolean", "description": "konumsuz genel raporları da ekle"}}),
    _fn("view_region",
        "Bir tespitin (D#) ya da tespiti olmayan bir kaydın (T####) çevresini yakın plan gösterir. "
        "Renk, yük, örtü, sınıf veya gerçekten araç olup olmadığını görerek kontrol etmek için.",
        {"target": {"type": "string", "description": "D# veya T####"},
         "question": {"type": "string"}}, ["target"]),
    _fn("get_track_points",
        "Bir kaydın 5 dakikalık tüm ham noktaları (saat, enlem, boylam, üsse uzaklık).",
        {"track_id": {"type": "string"}}, ["track_id"]),
    _fn("search_reports",
        "Tüm rapor havuzunda bir nokta çevresinde ve zaman aralığında arama (ham metin).",
        {"lat": {"type": "number"}, "lon": {"type": "number"}, "radius_m": {"type": "number"},
         "from_time": {"type": "string", "description": "HH:MM"}, "to_time": {"type": "string", "description": "HH:MM"}},
        ["lat", "lon"]),
]


def submit_schema(scene: Scene) -> dict:
    """submit_assessment built for this frame: vehicles and reports are keyed by their ids, and every
    vehicle / coordinate report that needs a decision is a required key. This makes skipping a vehicle
    or forgetting a report id a schema error instead of a silent omission."""
    required_v, optional_v = scene.subjects()
    coord_reports = [r["rid"] for r in scene.reports()["reports"] if r["scope"] == "koordinat"]
    other_reports = [r["rid"] for r in scene.reports()["reports"] if r["scope"] != "koordinat"]
    decision = {"type": "object", "properties": {
        "action": {"type": "string", "enum": ACTIONS},
        "confidence": {"type": "string", "enum": CONFIDENCE, "description": "kanıt yeterli ve tutarlı mı"},
        "reason": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}, "description": "dayanaklar: araç çıktısından aynen"}},
        "required": ["action", "confidence", "reason"]}
    verdict = {"type": "object", "properties": {
        "verdict": {"type": "string", "enum": REPORT_VERDICTS},
        "claims_checked": {"type": "array", "description": "raporun her iddiası ve ölçümle karşılaştırman",
                           "items": {"type": "object", "properties": {
                               "claim": {"type": "string"}, "finding": {"type": "string"}},
                               "required": ["claim", "finding"]}},
        "reason": {"type": "string"}},
        "required": ["verdict", "claims_checked", "reason"]}
    return _fn(
        "submit_assessment",
        "Nihai değerlendirmeni gönderir. Değerlendirmeyi bitirmenin tek yolu budur.",
        {"action": {"type": "string", "enum": ACTIONS, "description": "Kare için önerdiğin en acil eylem"},
         "headline": {"type": "string", "description": "Tek cümlelik özet"},
         "brief": {"type": "string", "description": "2-5 cümlelik değerlendirme; sayılar ve kaynaklarla"},
         "vehicles": {"type": "object", "description": "Araç kimliğine göre kararlar (D# veya tespiti olmayan T####). "
                                                      f"Zorunlu: {', '.join(required_v)}",
                      "properties": {vid: decision for vid in required_v + optional_v},
                      "required": required_v},
         "reports": {"type": "object", "description": "Rapor kimliğine göre değerlendirme. "
                                                     f"Zorunlu: {', '.join(coord_reports) or 'yok'}",
                     "properties": {rid: verdict for rid in coord_reports + other_reports},
                     "required": coord_reports},
         "uncertainties": {"type": "array", "items": {"type": "string"}}},
        ["action", "headline", "brief", "vehicles", "reports"])


def schemas(scene: Scene) -> list:
    return SCHEMAS + [submit_schema(scene)]


class ToolBox:
    """Tools bound to one frame."""

    def __init__(self, scene: Scene):
        self.s = scene

    def call(self, name: str, args: dict) -> tuple[str, str | None]:
        """Returns (JSON text for the model, optional image data-url to show it)."""
        fn = getattr(self, f"_t_{name}", None)
        if fn is None:
            return json.dumps({"error": f"bilinmeyen araç: {name}"}), None
        try:
            res, img = fn(**args)
        except TypeError as ex:
            return json.dumps({"error": f"geçersiz argüman: {ex}"}), None
        except KeyError as ex:
            return json.dumps({"error": f"bulunamadı: {ex}"}), None
        return json.dumps(res, ensure_ascii=False, default=list), img

    def _t_get_image_info(self):
        return self.s.info(), None

    def _t_detect_vehicles(self, min_conf: float = config.DET_CACHE_MIN_CONF):
        res = self.s.detections(min_conf)
        res["note"] = "Kutuların çizili hali bir sonraki mesajda (kesikli kutu = güven < 0.3)."
        return res, to_data_url(annotate(self.s, show_reports=False, min_conf=min_conf))

    def _t_match_tracks(self):
        return self.s.track_matches(), None

    def _t_get_motion(self, track_id: str | None = None, track_ids: list[str] | None = None):
        ids = list(track_ids or []) + ([track_id] if track_id else [])
        if not ids:
            raise TypeError("track_id veya track_ids gerekli")
        missing = [t for t in ids if t not in tracks()]
        if missing:
            raise KeyError(", ".join(missing))
        if len(ids) == 1:
            return self.s.motion(ids[0]), None
        return {"motions": [self.s.motion(t) for t in dict.fromkeys(ids)]}, None

    def _t_get_reports(self, radius_m: float = config.REPORT_RADIUS_M, lookback_min: int = config.REPORT_LOOKBACK_MIN,
                       include_general: bool = False):
        return self.s.reports(radius_m, lookback_min, include_general), None

    def _t_view_region(self, target: str, question: str = ""):
        d = self.s.detection(target)
        if d:
            center, box = d["center_px"], d["box_xywh"]
        else:
            t = next((t for t in self.s.track_matches()["tracks_in_frame_without_detection"] if t["track_id"] == target), None)
            if not t:
                tid_det = next((r["detection"] for r in self.s.track_matches()["matches"] if r["track_id"] == target), None)
                if not tid_det:
                    raise KeyError(target)
                d = self.s.detection(tid_det)
                center, box = d["center_px"], d["box_xywh"]
            else:
                center, box = t["center_px"], None
        im = crop(self.s.image_path, center, box)
        return {"target": target, "note": "Yakın plan bir sonraki mesajda; hedef görüntünün merkezinde."}, to_data_url(im)

    def _t_get_track_points(self, track_id: str):
        pts = tracks()[track_id]
        b = (self.s.info()["base"]["lat"], self.s.info()["base"]["lon"])
        return {"track_id": track_id,
                "points": [f"{p.time} {p.lat:.6f},{p.lon:.6f} üsse {haversine(p.pos, b):.0f} m" for p in pts]}, None

    def _t_search_reports(self, lat: float, lon: float, radius_m: float = 500, from_time: str = "00:00",
                          to_time: str = "23:59"):
        out = []
        for r in all_reports():
            if not (from_time <= r.time <= to_time):
                continue
            c = locate(r).coord
            if c and haversine(c, (lat, lon)) <= radius_m:
                out.append(dict(rid=r.rid, time=r.time, source=r.source, text=r.text,
                                dist_m=round(haversine(c, (lat, lon)))))
        return {"count": len(out), "reports": out[:20]}, None
