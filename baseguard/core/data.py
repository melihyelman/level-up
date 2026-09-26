"""Loading the given data files into simple typed structures."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache

from . import config
from .geo import Footprint, LatLon, haversine


def tmin(t: str) -> int:
    """'14:10' -> minutes since midnight."""
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def tstr(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


@dataclass
class ImageMeta:
    image_id: str
    width: int
    height: int
    time: str
    footprint: Footprint

    @property
    def tmin(self) -> int:
        return tmin(self.time)


@dataclass
class Zone:
    name: str
    center: LatLon


@dataclass
class TrackPoint:
    time: str
    lat: float
    lon: float

    @property
    def pos(self) -> LatLon:
        return self.lat, self.lon

    @property
    def tmin(self) -> int:
        return tmin(self.time)


@dataclass
class Report:
    rid: str
    time: str
    source: str  # official | third_party
    text: str

    @property
    def tmin(self) -> int:
        return tmin(self.time)


@lru_cache
def images() -> dict[str, ImageMeta]:
    raw = json.loads(config.IMAGE_META.read_text())
    return {k: ImageMeta(k, v["width_px"], v["height_px"], v["capture_time"],
                         Footprint(v["width_px"], v["height_px"], v["corner_coordinates"]))
            for k, v in raw.items()}


@lru_cache
def zones() -> tuple[LatLon, str, list[Zone]]:
    raw = json.loads(config.ZONES.read_text())
    b = raw["base"]
    return (b["lat"], b["lon"]), b["name"], [Zone(z["name"], tuple(z["center"])) for z in raw["zones"]]


def base() -> LatLon:
    return zones()[0]


def nearest_zone(p: LatLon) -> tuple[Zone, float]:
    zs = zones()[2]
    z = min(zs, key=lambda z: haversine(p, z.center))
    return z, haversine(p, z.center)


@lru_cache
def tracks() -> dict[str, list[TrackPoint]]:
    out: dict[str, list[TrackPoint]] = defaultdict(list)
    with open(config.TRACKS) as f:
        for r in csv.DictReader(f):
            out[r["track_id"]].append(TrackPoint(r["time"], float(r["lat"]), float(r["lon"])))
    for v in out.values():
        v.sort(key=lambda p: p.tmin)
    return dict(out)


@lru_cache
def reports() -> list[Report]:
    raw = json.loads(config.REPORTS.read_text())
    # stable ids in file order, so the agent can cite "R017"
    return [Report(f"R{i:03d}", r["time"], r["source"], r["text"]) for i, r in enumerate(raw)]
