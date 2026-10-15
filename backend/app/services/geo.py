"""Small geodesy helpers (no heavy GIS dependency needed for the MVP)."""
from __future__ import annotations

import math

import numpy as np

EARTH_R_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_R_KM * np.arcsin(np.sqrt(a))


def bbox_around(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * max(math.cos(math.radians(lat)), 0.01))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def cell_area_km2(lat: float, res_deg: float) -> float:
    return (res_deg * 111.32) * (res_deg * 111.32 * math.cos(math.radians(lat)))


def circle_polygon(lat: float, lon: float, radius_m: float, n: int = 64) -> list[list[float]]:
    pts = []
    for i in range(n + 1):
        a = 2 * math.pi * i / n
        dlat = (radius_m / 1000) / 111.32 * math.cos(a)
        dlon = (radius_m / 1000) / (111.32 * math.cos(math.radians(lat))) * math.sin(a)
        pts.append([lon + dlon, lat + dlat])
    return pts


class Grid:
    """Regular lat/lon grid. Row 0 is the NORTHERN edge (matches image/raster order)."""

    def __init__(self, bbox, res_deg: float):
        self.minlon, self.minlat, self.maxlon, self.maxlat = bbox
        self.res = res_deg
        self.width = max(1, int(math.ceil((self.maxlon - self.minlon) / res_deg)))
        self.height = max(1, int(math.ceil((self.maxlat - self.minlat) / res_deg)))
        # snap max edges to the grid
        self.maxlon = self.minlon + self.width * res_deg
        self.maxlat = self.minlat + self.height * res_deg

    @classmethod
    def from_shape(cls, minlon: float, maxlat: float, res: float, width: int, height: int) -> "Grid":
        g = cls.__new__(cls)
        g.minlon, g.maxlat, g.res, g.width, g.height = minlon, maxlat, res, int(width), int(height)
        g.maxlon = minlon + width * res
        g.minlat = maxlat - height * res
        return g

    @property
    def bbox(self):
        return [self.minlon, self.minlat, self.maxlon, self.maxlat]

    def centers(self):
        lons = self.minlon + (np.arange(self.width) + 0.5) * self.res
        lats = self.maxlat - (np.arange(self.height) + 0.5) * self.res
        LON, LAT = np.meshgrid(lons, lats)
        return LON, LAT

    def index(self, lat, lon):
        lat = np.asarray(lat, dtype=float)
        lon = np.asarray(lon, dtype=float)
        col = np.floor((lon - self.minlon) / self.res).astype(int)
        row = np.floor((self.maxlat - lat) / self.res).astype(int)
        inside = (col >= 0) & (col < self.width) & (row >= 0) & (row < self.height)
        return row, col, inside

    def cell_center(self, row: int, col: int):
        return (self.maxlat - (row + 0.5) * self.res, self.minlon + (col + 0.5) * self.res)

    def to_json(self, values: np.ndarray, nodata=None) -> dict:
        v = np.where(np.isfinite(values), np.round(values, 4), np.nan)
        return {
            "bbox": self.bbox,
            "res": self.res,
            "width": self.width,
            "height": self.height,
            "values": [None if not np.isfinite(x) else float(x) for x in v.ravel()],
        }
