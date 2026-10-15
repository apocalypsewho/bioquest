"""Land cover for habitat description in LIVE mode: ESA WorldCover 10 m (v200, 2021) read from local GeoTIFFs.

Product: Zanaga, D. et al. (2022) ESA WorldCover 10 m 2021 v200. https://doi.org/10.5281/zenodo.7254221
Tiles (3°×3°, named by their lower-left corner, e.g. ESA_WorldCover_10m_2021_v200_S12W078_Map.tif) are
public; download the ones you need with `python scripts/download_worldcover.py --bbox minlon minlat maxlon maxlat`.
Without tiles the provider reports "not available" and habitat stays "unknown" — nothing is invented.
"""
from __future__ import annotations

import math
import os
import re

import numpy as np

from ..config import get_settings

CLASSES = {
    10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland", 50: "Built-up",
    60: "Bare / sparse vegetation", 70: "Snow and ice", 80: "Permanent water bodies",
    90: "Herbaceous wetland", 95: "Mangroves", 100: "Moss and lichen",
}
SOURCE = "ESA WorldCover 10 m 2021 v200 (Zanaga et al. 2022)"
_TILE = re.compile(r"_([NS])(\d{2})([EW])(\d{3})_Map\.tif$")


def tile_name(lat: float, lon: float) -> str:
    la = int(math.floor(lat / 3) * 3)
    lo = int(math.floor(lon / 3) * 3)
    return (f"ESA_WorldCover_10m_2021_v200_{'N' if la >= 0 else 'S'}{abs(la):02d}"
            f"{'E' if lo >= 0 else 'W'}{abs(lo):03d}_Map.tif")


class WorldCoverProvider:
    code = "worldcover"
    label = "ESA WorldCover 10 m (local GeoTIFF tiles)"

    def __init__(self, directory: str | None = None):
        self.dir = directory or get_settings().landcover_dir

    def _files(self) -> list[str]:
        if not os.path.isdir(self.dir):
            return []
        return [os.path.join(self.dir, f) for f in sorted(os.listdir(self.dir)) if f.lower().endswith(".tif")]

    def available(self) -> tuple[bool, str]:
        try:
            import rasterio  # noqa: F401
        except ImportError:
            return False, "rasterio not installed"
        if not self._files():
            return False, f"no WorldCover tiles in {self.dir} (run scripts/download_worldcover.py)"
        return True, "ok"

    def _file_for(self, lat: float, lon: float) -> str | None:
        want = tile_name(lat, lon)
        files = self._files()
        for f in files:
            if os.path.basename(f) == want:
                return f
        import rasterio
        for f in files:  # any other GeoTIFF with WorldCover codes (e.g. a clipped mosaic)
            if _TILE.search(f):
                continue
            with rasterio.open(f) as src:
                b = src.bounds
                if b.left <= lon <= b.right and b.bottom <= lat <= b.top:
                    return f
        return None

    def summary(self, lat: float, lon: float, radius_m: float = 500) -> dict | None:
        """Class composition within radius_m of the point (None if no tile covers it)."""
        ok, _ = self.available()
        if not ok:
            return None
        path = self._file_for(lat, lon)
        if not path:
            return None
        import rasterio
        from rasterio.windows import from_bounds

        dlat = radius_m / 111_320
        dlon = radius_m / (111_320 * max(math.cos(math.radians(lat)), 0.01))
        with rasterio.open(path) as src:
            win = from_bounds(lon - dlon, lat - dlat, lon + dlon, lat + dlat, src.transform)
            win = win.round_offsets().round_lengths()
            arr = src.read(1, window=win, boundless=True, fill_value=0)
            t = src.window_transform(win)
            r, c = ~src.transform * (lon, lat)
        if arr.size == 0:
            return None
        rows, cols = np.indices(arr.shape)
        x = t.c + (cols + 0.5) * t.a
        y = t.f + (rows + 0.5) * t.e
        d = np.hypot((x - lon) * 111_320 * math.cos(math.radians(lat)), (y - lat) * 111_320)
        vals = arr[(d <= radius_m) & (arr > 0)]
        if vals.size == 0:
            return None
        codes, counts = np.unique(vals, return_counts=True)
        order = np.argsort(-counts)
        comp = [{"code": int(codes[i]), "class": CLASSES.get(int(codes[i]), f"code {int(codes[i])}"),
                 "fraction": round(float(counts[i] / vals.size), 3)} for i in order]
        return {"dominant": comp[0]["class"], "composition": comp[:5], "radius_m": round(radius_m),
                "source": SOURCE, "file": os.path.basename(path)}


_provider: WorldCoverProvider | None = None


def get_landcover() -> WorldCoverProvider:
    global _provider
    if _provider is None or _provider.dir != get_settings().landcover_dir:
        _provider = WorldCoverProvider()
    return _provider
