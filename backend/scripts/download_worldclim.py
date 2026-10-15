"""Download WorldClim v2.1 bioclimatic variables + elevation (real data) for LIVE modelling.

Source: https://www.worldclim.org/data/worldclim21.html  (files hosted at geodata.ucdavis.edu)
Citation: Fick, S.E. & Hijmans, R.J. (2017) Int. J. Climatol. 37: 4302–4315.
Resolutions: 10m (~18 km, ~50 MB bio zip), 5m, 2.5m, 30s (~10 GB). 10m is recommended for the MVP.

Usage:  python scripts/download_worldclim.py --res 10m
"""
import argparse
import io
import os
import sys
import urllib.request
import zipfile

BASE = "https://geodata.ucdavis.edu/climate/worldclim/2_1/base"
KEEP = {"bio_1", "bio_4", "bio_12", "bio_15", "elev"}


def fetch(url: str) -> bytes:
    print(f"Downloading {url} ...", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "BIOQUEST/0.1"})
    with urllib.request.urlopen(req) as r:
        return r.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", default="10m", choices=["10m", "5m", "2.5m", "30s"])
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "data", "worldclim"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for kind in ("bio", "elev"):
        data = fetch(f"{BASE}/wc2.1_{a.res}_{kind}.zip")
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                stem = name.rsplit("/", 1)[-1].removesuffix(".tif").split(f"wc2.1_{a.res}_")[-1]
                if stem in KEEP:
                    target = os.path.join(a.out, name.rsplit("/", 1)[-1])
                    with open(target, "wb") as f:
                        f.write(z.read(name))
                    print("  saved", target)
    print("Done. Set BIOQUEST_ENV_PROVIDER=worldclim (default for LIVE modelling).")


if __name__ == "__main__":
    sys.exit(main())
