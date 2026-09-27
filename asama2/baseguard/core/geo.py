"""Geometry helpers: pixel <-> WGS84, distances, bearings."""
from __future__ import annotations

import math

R_EARTH = 6_371_000.0
COMPASS_TR = ["kuzey", "kuzeydoğu", "doğu", "güneydoğu", "güney", "güneybatı", "batı", "kuzeybatı"]

LatLon = tuple[float, float]


def haversine(a: LatLon, b: LatLon) -> float:
    """Distance in metres."""
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(h))


def bearing(a: LatLon, b: LatLon) -> float:
    """Initial bearing a->b in degrees, 0 = north, clockwise."""
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def compass(deg: float) -> str:
    return COMPASS_TR[int((deg + 22.5) // 45) % 8]


def angle_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d


class Footprint:
    """Image ground footprint. Brief: nadir view, top edge north, left edge west -> linear mapping."""

    def __init__(self, width_px: int, height_px: int, corners: dict):
        self.W, self.H = width_px, height_px
        self.tl = tuple(corners["top_left"]); self.tr = tuple(corners["top_right"])
        self.bl = tuple(corners["bottom_left"]); self.br = tuple(corners["bottom_right"])

    def to_geo(self, x: float, y: float) -> LatLon:
        lon = self.tl[1] + (x / self.W) * (self.tr[1] - self.tl[1])
        lat = self.tl[0] + (y / self.H) * (self.bl[0] - self.tl[0])
        return lat, lon

    def to_px(self, p: LatLon) -> tuple[float, float]:
        x = (p[1] - self.tl[1]) / (self.tr[1] - self.tl[1]) * self.W
        y = (p[0] - self.tl[0]) / (self.bl[0] - self.tl[0]) * self.H
        return x, y

    @property
    def center(self) -> LatLon:
        return (self.tl[0] + self.br[0]) / 2, (self.tl[1] + self.br[1]) / 2

    @property
    def width_m(self) -> float:
        return haversine(self.tl, self.tr)

    @property
    def height_m(self) -> float:
        return haversine(self.tl, self.bl)

    @property
    def m_per_px(self) -> float:
        return (self.width_m / self.W + self.height_m / self.H) / 2

    def contains(self, p: LatLon, margin_m: float = 0.0) -> bool:
        return self.dist_outside(p) <= margin_m

    def dist_outside(self, p: LatLon) -> float:
        """0 if inside, else distance in metres to the nearest footprint edge."""
        lat = min(max(p[0], self.bl[0]), self.tl[0])
        lon = min(max(p[1], self.tl[1]), self.tr[1])
        return haversine(p, (lat, lon))
