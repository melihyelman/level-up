"""Field reports: locating them in space and time relative to an image.

Only *where* and *when* a report points is computed here. What the report claims, and whether it
is true, is left to the agent: it reads the raw text and compares it with the measurements.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import config
from .data import ImageMeta, Report, nearest_zone, reports, zones
from .geo import LatLon, haversine

COORD_RE = re.compile(r"(\d{2}\.\d+)\s*N\s+(\d{2}\.\d+)\s*E")


def _norm(s: str) -> str:
    return s.translate(str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")).lower()


@dataclass
class Location:
    coord: LatLon | None
    coord_decimals: int
    zone: str | None


def locate(r: Report) -> Location:
    m = COORD_RE.search(r.text)
    coord, dec = None, 0
    if m:
        coord = (float(m.group(1)), float(m.group(2)))
        dec = min(len(m.group(1).split(".")[1]), len(m.group(2).split(".")[1]))
    t = _norm(r.text)
    zone = next((z.name for z in zones()[2] if _norm(z.name) in t), None)
    return Location(coord, dec, zone)


@dataclass
class RelevantReport:
    report: Report
    loc: Location
    scope: str               # "koordinat" (a point near the frame) | "bölge" (names the frame's zone) | "genel"
    dist_to_frame_m: float | None   # 0 = the point is inside the frame
    age_min: int             # capture time - report time (negative = report came after capture)
    px: tuple[int, int] | None = None


def relevant(img: ImageMeta, radius_m: float = config.REPORT_RADIUS_M,
             lookback_min: int = config.REPORT_LOOKBACK_MIN, include_general: bool = False) -> list[RelevantReport]:
    """Reports in the time window whose coordinate lies within radius_m of the frame, or that name the
    frame's nearest zone. With include_general, also reports with no location at all."""
    fp = img.footprint
    my_zone, _ = nearest_zone(fp.center)
    out = []
    for r in reports():
        age = img.tmin - r.tmin
        if age > lookback_min or age < -30:
            continue
        loc = locate(r)
        if loc.coord:
            d = fp.dist_outside(loc.coord)
            if d <= radius_m:
                out.append(RelevantReport(r, loc, "koordinat", round(d), age,
                                          tuple(round(v) for v in fp.to_px(loc.coord))))
        elif loc.zone == my_zone.name:
            out.append(RelevantReport(r, loc, "bölge", None, age))
        elif include_general and not loc.zone:
            out.append(RelevantReport(r, loc, "genel", None, age))
    out.sort(key=lambda x: ({"koordinat": 0, "bölge": 1, "genel": 2}[x.scope], x.dist_to_frame_m or 0, x.age_min))
    return out


# ---------------------------------------------------------------- claims (parsing only, no verdicts)

TYPE_WORDS = [("agir arac", "heavy"), ("agir bir arac", "heavy"), ("kamyon", "truck"), ("otobus", "bus"),
              ("panelvan", "van"), ("minibus", "van"), ("otomobil", "car"), ("binek", "car")]
HEAVY = {"truck", "bus"}
COLORS = ["mavi", "kirmizi", "sari", "beyaz", "siyah", "yesil", "gri"]


@dataclass
class Claims:
    vtype: str | None = None       # car | van | truck | bus | heavy
    count: int | None = None       # explicit number ("5 kamyon"); None for "bir kamyon"
    stationary: bool = False       # "hareketsiz", "durdugu", "beklemede", "park halinde"...
    moving: bool = False           # "ilerliyor", "transit", "hareketleri olagan"
    approaching: bool = False      # "usse dogru", "usse gelen"
    leaving: bool = False          # "uzaklasiyor"
    identity: bool = False         # "dost", "bize bagli", "planli ikmal", "kimlik teyidi"
    color: str | None = None
    cargo: bool = False            # "yuklu", "uzeri ortulu"
    baseline_count: int | None = None  # "normalde ~4 arac" style statements
    busier_than_usual: bool = False


def claims(r: Report) -> Claims:
    t = _norm(r.text)
    c = Claims()
    c.vtype = next((k for w, k in TYPE_WORDS if w in t), None)
    m = re.search(r"(\d+)\s+arac(?:lik)?\s+bir\s+\w+\s+konvoy", t) or \
        re.search(r"(\d+)\s+(?:kamyon|agir arac|arac|otomobil|panelvan|otobus)", t)
    if "genellikle" in t or "olagan trafik" in t:
        c.baseline_count = int(m.group(1)) if m else None
        c.busier_than_usual = "yogun" in t
    elif m:
        c.count = int(m.group(1))
    c.stationary = any(w in t for w in ["hareketsiz", "yerinden ayrilmadi", "durdugu", "beklemede", "bekliyor", "park halinde"])
    c.approaching = any(w in t for w in ["usse dogru", "usse gelen"])
    c.leaving = "uzaklasiyor" in t
    c.moving = c.approaching or c.leaving or any(w in t for w in ["ilerliyor", "transit", "hareketleri olagan"])
    c.identity = any(w in t for w in ["dost", "bize bagli", "planli ikmal", "kimlik teyid", "teyitli"])
    c.color = next((w for w in COLORS if w in t), None)
    c.cargo = any(w in t for w in ["yuklu", "uzeri ortulu"])
    return c
