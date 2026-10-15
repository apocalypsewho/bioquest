"""SamplingGapService: transparent Sampling Gap Score per grid cell.

Input: "effort records" = observations of ANY taxon in the area ({lat, lon, observer, taxon, rank, year}).
They measure how much people have looked, not what lives there.

Sampling Gap Score (0–100, higher = less sampled) = weighted sum of
  effort       35%  1 − log(1+n_records)/log(1+n_ref)            (n_ref = 95th pct of non-empty cells)
  observers    15%  1 − log(1+n_observers)/log(1+obs_ref)
  distance     20%  min(distance to nearest record / (2 × cell size), 1)
  temporal     15%  1 − min(distinct years / 10, 1)
  coverage     15%  1 − fraction of the cell's 3×3 sub-cells containing any record

Interpretation guard: few records ≠ low biodiversity. A cell is labelled
  UNDER-SAMPLED                      gap ≥ 60 → known richness says little about real richness
  SAMPLED · LOW KNOWN RICHNESS       gap < 60 and species/record ratio in the lowest tercile
  SAMPLED                            otherwise
"""
from __future__ import annotations

import numpy as np

from .geo import Grid, haversine_km

WEIGHTS = {"effort": 0.35, "observers": 0.15, "distance": 0.20, "temporal": 0.15, "coverage": 0.15}


def compute_gap(records: list[dict], grid: Grid) -> dict:
    H, W = grid.height, grid.width
    n = np.zeros((H, W))
    obs_sets = [[set() for _ in range(W)] for _ in range(H)]
    tax_sets = [[set() for _ in range(W)] for _ in range(H)]
    yr_sets = [[set() for _ in range(W)] for _ in range(H)]
    unresolved = np.zeros((H, W))
    sub = np.zeros((H, W, 9), dtype=bool)
    if records:
        lat = np.array([r["lat"] for r in records])
        lon = np.array([r["lon"] for r in records])
        row, col, inside = grid.index(lat, lon)
        for i in np.nonzero(inside)[0]:
            a, b = row[i], col[i]
            r = records[i]
            n[a, b] += 1
            if r.get("observer"):
                obs_sets[a][b].add(r["observer"])
            if r.get("taxon"):
                tax_sets[a][b].add(r["taxon"])
            if r.get("year"):
                yr_sets[a][b].add(r["year"])
            if r.get("rank") and r["rank"] not in ("species", "subspecies", "variety"):
                unresolved[a, b] += 1
            fx = (lon[i] - (grid.minlon + b * grid.res)) / grid.res
            fy = ((grid.maxlat - a * grid.res) - lat[i]) / grid.res
            sub[a, b, min(int(fy * 3), 2) * 3 + min(int(fx * 3), 2)] = True
    obs = np.array([[len(s) for s in row_] for row_ in obs_sets], dtype=float)
    rich = np.array([[len(s) for s in row_] for row_ in tax_sets], dtype=float)
    years = np.array([[len(s) for s in row_] for row_ in yr_sets], dtype=float)

    nz = n[n > 0]
    n_ref = max(np.percentile(nz, 95), 1) if nz.size else 1
    o_ref = max(np.percentile(obs[obs > 0], 95), 1) if (obs > 0).any() else 1
    c_effort = np.clip(1 - np.log1p(n) / np.log1p(n_ref), 0, 1)
    c_obs = np.clip(1 - np.log1p(obs) / np.log1p(o_ref), 0, 1)
    c_temp = 1 - np.clip(years / 10, 0, 1)
    c_cov = 1 - sub.mean(-1)

    LON, LAT = grid.centers()
    cell_km = grid.res * 111.32
    if records:
        rl = np.array([r["lat"] for r in records])
        ro = np.array([r["lon"] for r in records])
        if len(rl) > 3000:
            sel = np.random.default_rng(0).choice(len(rl), 3000, replace=False)
            rl, ro = rl[sel], ro[sel]
        d = np.empty((H, W))
        for a in range(H):
            d[a] = haversine_km(LAT[a][:, None], LON[a][:, None], rl[None, :], ro[None, :]).min(1)
    else:
        d = np.full((H, W), np.inf)
    c_dist = np.clip(d / (2 * cell_km), 0, 1)

    comps = {"effort": c_effort, "observers": c_obs, "distance": c_dist, "temporal": c_temp, "coverage": c_cov}
    gap = 100 * sum(WEIGHTS[k] * v for k, v in comps.items())

    ratio = np.where(n > 0, rich / np.maximum(n, 1), np.nan)
    low_ratio = np.nanpercentile(ratio, 33) if np.isfinite(ratio).any() else 0
    cls = np.where(gap >= 60, "UNDER-SAMPLED",
                   np.where(np.nan_to_num(ratio, nan=1) <= low_ratio, "SAMPLED · LOW KNOWN RICHNESS", "SAMPLED"))
    return {
        "grid": grid,
        "gap": gap,
        "components": comps,
        "n_records": n,
        "n_observers": obs,
        "richness": rich,
        "years": years,
        "unresolved_fraction": np.where(n > 0, unresolved / np.maximum(n, 1), np.nan),
        "distance_km": d,
        "class": cls,
        "weights": WEIGHTS,
        "taxa_sets": tax_sets,
        "taxon_counts": _taxon_counts(records),
    }


def _taxon_counts(records: list[dict]) -> dict:
    c: dict = {}
    for r in records:
        if r.get("taxon"):
            c[r["taxon"]] = c.get(r["taxon"], 0) + 1
    return c


def intensity_label(gap: float) -> str:
    return "LOW" if gap >= 60 else ("MEDIUM" if gap >= 35 else "HIGH")


def cell_report(g: dict, a: int, b: int) -> dict:
    return {
        "sampling_gap_score": round(float(g["gap"][a, b]), 1),
        "sampling_intensity": intensity_label(float(g["gap"][a, b])),
        "class": str(g["class"][a, b]),
        "records": int(g["n_records"][a, b]),
        "observers": int(g["n_observers"][a, b]),
        "known_taxa": int(g["richness"][a, b]),
        "distinct_years": int(g["years"][a, b]),
        "distance_to_nearest_record_km": round(float(g["distance_km"][a, b]), 2),
        "components": {k: round(float(v[a, b]) * 100, 1) for k, v in g["components"].items()},
        "weights": g["weights"],
        "note": "Few records indicate low sampling effort, not low biodiversity.",
    }
