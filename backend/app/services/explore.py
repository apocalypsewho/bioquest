"""Opportunity detection (EXPLORE) and species-specific exploration zones.

Selection is deterministic: the highest ExplorationPriorityScore among candidate cells — never random.
"""
from __future__ import annotations

import math

import numpy as np

from . import hub
from .access import get_access, road_access_score
from .landcover import get_landcover
from .environment import NotConfigured, get_provider
from .geo import Grid, bbox_around, cell_area_km2, circle_polygon, haversine_km
from .priority import EXPLORE_WEIGHTS, accessibility, accessibility_label, biodiversity_potential, score
from .sampling import cell_report, compute_gap
from .types import DEMO, LIVE, MODEL


def _env_for(mode: str):
    """Environment provider consistent with the data mode (never mix DEMO env with LIVE data)."""
    if mode == "demo":
        return get_provider("demo")
    p = get_provider("worldclim")
    ok, _ = p.available()
    return p if ok else None


def _slope_elev(provider, grid: Grid):
    if not provider:
        return None, None
    try:
        env = provider.grid(grid, ["elev", "slope"])
        return env.get("slope"), env.get("elev")
    except NotConfigured:
        return None, None


def _habitat(mode: str, lat: float, lon: float, elev, radius_m: float = 500) -> dict:
    if mode == "demo":
        return hub.demo.habitat(lat, lon)
    el = round(float(elev)) if elev is not None and np.isfinite(elev) else None
    src = ["Elevation: WorldClim v2.1"] if el is not None else []
    lc = None
    try:
        lc = get_landcover().summary(lat, lon, min(radius_m, 2000))
    except Exception as e:  # unreadable tile: say so, do not invent a habitat
        src.append(f"land cover unreadable ({e.__class__.__name__})")
    if lc:
        return {"elevation_m": el, "habitat": lc["dominant"], "land_cover": lc["composition"],
                "source": "; ".join(src + [f"Land cover: {lc['source']}"])}
    return {"elevation_m": el, "habitat": "unknown (no land-cover tile for this area; run "
                                         "scripts/download_worldcover.py)",
            "source": "; ".join(src) or "no environmental layer configured for LIVE mode"}


async def _add_road_access(zone: dict, mode: str) -> None:
    c = zone["center"]
    info = await get_access().nearest_ways(mode, c["lat"], c["lon"])
    zone["road_access"] = info
    v = road_access_score(info)
    if v is not None:
        zone["accessibility"]["road_score"] = round(v)
        zone["accessibility"]["method"] = ("ranking: proxy (straight-line distance + slope); zone: distance to "
                                           "nearest mapped road/trail (" + info["source"] + ")")


def _grid_payload(grid: Grid, layer: np.ndarray) -> dict:
    return grid.to_json(layer)


async def explore(mode: str, lat: float, lon: float, radius_km: float = 20.0) -> dict:
    bbox = bbox_around(lat, lon, radius_km)
    res = round(max(radius_km * 2 / 14 / 111.32, 0.01), 3)
    grid = Grid(bbox, res)
    effort = await hub.effort_records(bbox, mode)
    if mode == "live" and effort["errors"] and not effort["records"]:
        return {"status": "error", "errors": effort["errors"],
                "message": "Live data sources are unreachable, so no opportunity can be computed. "
                           "Switch to DEMO MODE to try the workflow with fictitious data."}
    g = compute_gap(effort["records"], grid)
    env = _env_for(mode)
    slope, elev = _slope_elev(env, grid)
    LON, LAT = grid.centers()
    dist = haversine_km(lat, lon, LAT, LON)
    bio, bio_parts = biodiversity_potential(g, elev)

    cands = []
    for a in range(grid.height):
        for b in range(grid.width):
            if dist[a, b] > radius_km or dist[a, b] < res * 111.32 * 0.5:
                continue
            acc = accessibility(dist[a, b], None if slope is None else slope[a, b], radius_km * 1.5)
            unres = g["unresolved_fraction"][max(a - 1, 0):a + 2, max(b - 1, 0):b + 2]
            unres_v = float(np.nanmean(unres) * 100) if np.isfinite(unres).any() else None
            comps = {"suitability": None, "model_agreement": None, "sampling_gap": float(g["gap"][a, b]),
                     "biodiversity_potential": float(bio[a, b]), "accessibility": acc,
                     "taxonomic_uncertainty": unres_v}
            cands.append((score(comps, EXPLORE_WEIGHTS), a, b, acc))
    if not cands:
        return {"status": "error", "message": "No candidate cells in range."}
    cands.sort(key=lambda c: (-c[0]["score"], dist[c[1], c[2]]))
    best = cands[0]
    zone = _zone(mode, grid, g, best, dist, elev, lat, lon, kind="explore", bio_parts=bio_parts)
    zone["effort_note"] = effort["note"]
    await _add_road_access(zone, mode)
    signals = [{"lat": float(LAT[a, b]), "lon": float(LON[a, b]), "score": s["score"]} for s, a, b, _ in cands[1:7]]
    return {
        "status": "ok",
        "provenance": DEMO if mode == "demo" else LIVE,
        "score_provenance": MODEL,
        "zone": zone,
        "signals": signals,
        "gap_layer": _grid_payload(grid, g["gap"]),
        "stats": {
            "observations_nearby": int(g["n_records"].sum()),
            "taxa_recorded": int(len({r["taxon"] for r in effort["records"] if r.get("taxon")})),
            "undersampled_cells": int((g["gap"] >= 60).sum()),
            "cells": int(grid.width * grid.height),
            "effort_complete": effort["complete"],
        },
        "errors": effort["errors"],
    }


def _zone(mode, grid, g, best, dist, elev, ulat, ulon, kind: str, extra: dict | None = None,
          bio_parts: dict | None = None) -> dict:
    s, a, b, acc = best
    if bio_parts:
        for c in s["components"]:
            if c["key"] == "biodiversity_potential":
                c["parts"] = {k: (None if not np.isfinite(v[a, b]) else round(float(v[a, b])))
                              for k, v in bio_parts.items()}
    clat, clon = grid.cell_center(a, b)
    radius_m = grid.res * 111_320 * 0.5
    e = None if elev is None else elev[a, b]
    gap = cell_report(g, a, b)
    headline = {"LOW": "Potentially under-sampled habitat",
                "MEDIUM": "Moderately sampled area",
                "HIGH": "Well-sampled area: improve records and identifications"}[gap["sampling_intensity"]]
    return {
        "kind": kind,
        "headline": headline,
        "center": {"lat": round(clat, 5), "lon": round(clon, 5)},
        "radius_m": round(radius_m),
        "polygon": circle_polygon(clat, clon, radius_m),
        "area_km2": round(math.pi * (radius_m / 1000) ** 2, 2),
        "cell_area_km2": round(cell_area_km2(clat, grid.res), 2),
        "distance_km": round(float(dist[a, b]), 1),
        "accessibility": {"value": round(acc), "label": accessibility_label(acc),
                          "method": "proxy: straight-line distance + slope"},
        "habitat": _habitat(mode, clat, clon, e, radius_m),
        "sampling": gap,
        "priority": s,
        "biodiversity_label": "High biodiversity potential" if (s["components"][3]["value"] or 0) >= 60
        else "Moderate biodiversity potential",
        "provenance": DEMO if mode == "demo" else LIVE,
        **(extra or {}),
    }


async def species_zone(mode: str, run, preds: dict, known_points: list[tuple[float, float]],
                       ulat: float | None, ulon: float | None, max_km: float = 120.0) -> dict:
    """Best exploration zone for a modelled species (ensemble + agreement + gap + access)."""
    ens_g = preds["ensemble"]
    grid = Grid.from_shape(ens_g["bbox"][0], ens_g["bbox"][3], ens_g["res"], ens_g["width"], ens_g["height"])
    ens = np.array([np.nan if v is None else v for v in ens_g["values"]]).reshape(grid.height, grid.width)
    agr_g = preds["agreement"]
    agr = np.array([np.nan if v is None else v for v in agr_g["values"]]).reshape(grid.height, grid.width)
    n_models = int(run.metrics.get("ensemble", {}).get("n_models", 3))
    thr = run.metrics.get("ensemble", {}).get("threshold_p10", 0.5)
    LON, LAT = grid.centers()

    if ulat is None:
        a0, b0 = np.unravel_index(np.nanargmax(ens), ens.shape)
        ulat, ulon = float(LAT[a0, b0]), float(LON[a0, b0])
        origin = "highest-suitability cell (no user location given)"
    else:
        origin = "your location"
    dist = haversine_km(ulat, ulon, LAT, LON)
    mask = np.isfinite(ens) & (ens >= thr) & (dist <= max_km)
    if not mask.any():
        return {"status": "none", "message": f"No suitable cells (≥ p10 training threshold) within {max_km:.0f} km "
                                             f"of {origin}."}
    # sub-window around candidate cells for effort data (bounded size)
    rows, cols = np.nonzero(mask)
    a1, a2 = rows.min(), rows.max() + 1
    b1, b2 = cols.min(), cols.max() + 1
    while (a2 - a1) * (b2 - b1) * grid.res ** 2 > 2.5:  # cap area ≈ 2.5 deg² to bound API calls
        if a2 - a1 > b2 - b1:
            a1, a2 = (a1 + 1, a2) if abs(LAT[a1, 0] - ulat) > abs(LAT[a2 - 1, 0] - ulat) else (a1, a2 - 1)
        else:
            b1, b2 = (b1 + 1, b2) if abs(LON[0, b1] - ulon) > abs(LON[0, b2 - 1] - ulon) else (b1, b2 - 1)
    sub = Grid.from_shape(grid.minlon + b1 * grid.res, grid.maxlat - a1 * grid.res, grid.res, b2 - b1, a2 - a1)
    effort = await hub.effort_records(sub.bbox, mode)
    g = compute_gap(effort["records"], sub)
    env = _env_for(mode)
    slope, elev = _slope_elev(env, sub)
    bio, bio_parts = biodiversity_potential(g, elev)
    kp = np.array(known_points) if known_points else np.empty((0, 2))
    cands = []
    for a in range(sub.height):
        for b in range(sub.width):
            A, B = a + a1, b + b1
            if not mask[A, B]:
                continue
            acc = accessibility(dist[A, B], None if slope is None else slope[a, b], max_km)
            unres = g["unresolved_fraction"][max(a - 1, 0):a + 2, max(b - 1, 0):b + 2]
            comps = {
                "suitability": float(ens[A, B] * 100),
                "model_agreement": float(agr[A, B] / max(n_models, 1) * 100),
                "sampling_gap": float(g["gap"][a, b]),
                "biodiversity_potential": float(bio[a, b]),
                "accessibility": acc,
                "taxonomic_uncertainty": float(np.nanmean(unres) * 100) if np.isfinite(unres).any() else None,
            }
            cands.append((score(comps), a, b, acc))
    if not cands:
        return {"status": "none", "message": "No candidate cells."}
    cands.sort(key=lambda c: -c[0]["score"])
    best = cands[0]
    s, a, b, _ = best
    clat, clon = sub.cell_center(a, b)
    d_known = float(haversine_km(clat, clon, kp[:, 0], kp[:, 1]).min()) if len(kp) else None
    outside = d_known is None or d_known > sub.res * 111.32
    sub_dist = dist[a1:a2, b1:b2]
    zone = _zone(mode, sub, g, best, sub_dist, elev, ulat, ulon, kind="species", bio_parts=bio_parts, extra={
        "target": {"key": run.taxon_key, "scientific_name": run.scientific_name},
        "environmental_suitability": round(float(ens[a + a1, b + b1]), 3),
        "model_agreement": f"{int(agr[a + a1, b + b1])}/{n_models}",
        "distance_to_nearest_known_record_km": None if d_known is None else round(d_known, 1),
        "objective": ("Find evidence of presence outside the known distribution." if outside
                      else "Document the species at an under-sampled site within its known range."),
        "model_run_id": run.id,
        "distance_origin": origin,
    })
    zone["effort_note"] = effort["note"]
    await _add_road_access(zone, mode)
    zone["provenance"] = MODEL + (" · DEMO input" if mode == "demo" else " · LIVE input")
    return {"status": "ok", "zone": zone, "alternatives": [
        {"lat": sub.cell_center(x[1], x[2])[0], "lon": sub.cell_center(x[1], x[2])[1], "score": x[0]["score"]}
        for x in cands[1:6]], "gap_layer": sub.to_json(g["gap"]), "errors": effort["errors"]}
