"""Distance to roads and trails for an exploration zone.

LIVE: OpenStreetMap via the Overpass API (https://wiki.openstreetmap.org/wiki/Overpass_API).
      One query per selected zone (not per candidate cell), so the ranking still uses the proxy
      (straight-line distance + slope) and the zone card adds the real road/trail distance.
DEMO: the fictitious road of the DEMO region (lat ≈ -12.0), labelled DEMO.
If Overpass is unreachable the zone keeps the proxy and the error is shown — never a made-up road.
"""
from __future__ import annotations

import math

import numpy as np

from ..config import get_settings
from .geo import haversine_km
from .http import ThrottledClient, UpstreamError

ROADS = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "service", "track"}
TRAILS = {"path", "footway", "bridleway", "steps", "cycleway"}
OSM_ATTRIBUTION = "© OpenStreetMap contributors (ODbL), via Overpass API"


def _seg_dist_km(lat, lon, la1, lo1, la2, lo2) -> float:
    """Point-to-segment distance on a local equirectangular projection (fine at < 50 km)."""
    k = math.cos(math.radians(lat))
    px, py = lon * k, lat
    ax, ay, bx, by = lo1 * k, la1, lo2 * k, la2
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy)) * 111.32


def nearest_from_overpass(data: dict, lat: float, lon: float) -> dict:
    best = {"road": None, "trail": None}
    for el in data.get("elements", []):
        hw = (el.get("tags") or {}).get("highway")
        kind = "road" if hw in ROADS else "trail" if hw in TRAILS else None
        geom = el.get("geometry") or []
        if not kind or len(geom) < 1:
            continue
        pts = [(g["lat"], g["lon"]) for g in geom]
        if len(pts) == 1:
            pts = pts * 2
        d = min(_seg_dist_km(lat, lon, *pts[i], *pts[i + 1]) for i in range(len(pts) - 1))
        cur = best[kind]
        if cur is None or d < cur["distance_km"]:
            best[kind] = {"distance_km": round(d, 2), "highway": hw, "name": (el.get("tags") or {}).get("name"),
                          "osm_way_id": el.get("id")}
    return best


class AccessibilityProvider:
    def __init__(self):
        s = get_settings()
        self.url = s.overpass_url
        self.client = ThrottledClient("OpenStreetMap Overpass", s.overpass_url, 1.0)
        self._cache: dict = {}

    async def nearest_ways(self, mode: str, lat: float, lon: float, search_km: float = 10.0) -> dict:
        if mode == "demo":
            d = float(haversine_km(lat, lon, -12.0, lon))
            return {"status": "ok", "provenance": "DEMO DATA", "source": "DEMO fictitious road (lat −12.0)",
                    "road": {"distance_km": round(d, 2), "highway": "track", "name": "DEMO road"}, "trail": None,
                    "search_radius_km": search_km}
        key = (round(lat, 3), round(lon, 3), search_km)
        if key in self._cache:
            return self._cache[key]
        r = int(search_km * 1000)
        q = f'[out:json][timeout:25];way(around:{r},{lat:.5f},{lon:.5f})["highway"];out tags geom;'
        try:
            data = await self.client.request("POST", self.url, data={"data": q})
        except UpstreamError as e:
            return {"status": "error", "error": {"service": e.service, "detail": e.detail},
                    "message": "Road network unavailable; accessibility uses the straight-line + slope proxy."}
        best = nearest_from_overpass(data, lat, lon)
        out = {"status": "ok", "provenance": "LIVE DATA", "source": OSM_ATTRIBUTION, **best,
               "search_radius_km": search_km,
               "note": None if best["road"] or best["trail"] else
               f"No mapped road or trail within {search_km:.0f} km in OpenStreetMap (may be unmapped, not absent)."}
        self._cache[key] = out
        return out


def road_access_score(info: dict) -> float | None:
    """0–100 from distance to the nearest road/trail (walking: 0 km → 100, ≥ 8 km → 0)."""
    if info.get("status") != "ok":
        return None
    ds = [w["distance_km"] for w in (info.get("road"), info.get("trail")) if w]
    if not ds:
        return 0.0
    return float(np.clip(100 * (1 - min(ds) / 8.0), 0, 100))


_acc: AccessibilityProvider | None = None


def get_access() -> AccessibilityProvider:
    global _acc
    if _acc is None:
        _acc = AccessibilityProvider()
    return _acc
