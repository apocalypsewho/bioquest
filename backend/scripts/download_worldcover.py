"""Download ESA WorldCover 10 m 2021 v200 tiles (real land-cover data) covering a bounding box.

Tiles are 3°×3° (~50–150 MB each) served from the public AWS Open Data bucket `esa-worldcover`.
Citation: Zanaga, D. et al. (2022) ESA WorldCover 10 m 2021 v200. https://doi.org/10.5281/zenodo.7254221

Usage:  python scripts/download_worldcover.py --bbox -76 -13 -74 -11
"""
import argparse
import math
import os
import sys
import urllib.request

BASE = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"


def tiles(minlon, minlat, maxlon, maxlat):
    for la in range(int(math.floor(minlat / 3) * 3), int(math.ceil(maxlat / 3) * 3), 3):
        for lo in range(int(math.floor(minlon / 3) * 3), int(math.ceil(maxlon / 3) * 3), 3):
            yield (f"ESA_WorldCover_10m_2021_v200_{'N' if la >= 0 else 'S'}{abs(la):02d}"
                   f"{'E' if lo >= 0 else 'W'}{abs(lo):03d}_Map.tif")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("MINLON", "MINLAT", "MAXLON", "MAXLAT"))
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "data", "worldcover"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for name in tiles(*a.bbox):
        target = os.path.join(a.out, name)
        if os.path.exists(target):
            print("  exists", target)
            continue
        url = f"{BASE}/{name}"
        print(f"Downloading {url} ...", flush=True)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "BIOQUEST/0.1"})
            with urllib.request.urlopen(req) as r, open(target + ".part", "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            os.replace(target + ".part", target)
            print("  saved", target)
        except Exception as e:  # ocean-only tiles do not exist
            print(f"  skipped {name}: {e}")
    print("Done. Habitat in LIVE mode will now use ESA WorldCover.")


if __name__ == "__main__":
    sys.exit(main())
