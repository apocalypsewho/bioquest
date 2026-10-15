"""Unusual-observation screening: compares a user's record with known occurrences and the model.

Output is a SUGGESTED flag with reasons — never a certification. The user (and ultimately a specialist)
decides whether to file a Discovery. Typical false alarms: misidentification, obscured public coordinates
of known records, incomplete public data, or a model trained on few records.
"""
from __future__ import annotations

import numpy as np

from .geo import Grid, haversine_km

RANGE_EXTENSION_KM = 100.0
ELEV_MARGIN_M = 300.0
DISCLAIMER = ("Automatic screening, not a certification. Confirm the identification first; known records may be "
              "incomplete or have obscured coordinates. Only a specialist can confirm a range extension.")


def _suitability_at(pred_grid: dict, lat: float, lon: float) -> float | None:
    g = Grid.from_shape(pred_grid["bbox"][0], pred_grid["bbox"][3], pred_grid["res"], pred_grid["width"],
                        pred_grid["height"])
    r, c, inside = g.index([lat], [lon])
    if not inside[0]:
        return None
    v = pred_grid["values"][int(r[0]) * g.width + int(c[0])]
    return None if v is None else float(v)


def assess(lat: float, lon: float, altitude_m: float | None, known: list[dict], model: dict | None,
           range_km: float = RANGE_EXTENSION_KM) -> dict:
    """known: [{lat, lon, elevation_m?}] VALID records; model: {grid, threshold, run_id, provenance} or None."""
    flags, reasons, facts = [], [], {}
    facts["known_valid_records"] = len(known)
    if known:
        kl = np.array([[k["lat"], k["lon"]] for k in known])
        d = haversine_km(lat, lon, kl[:, 0], kl[:, 1])
        dmin = float(np.min(d))
        facts["distance_to_nearest_known_record_km"] = round(dmin, 1)
        if dmin > range_km:
            flags.append("POTENTIAL RANGE EXTENSION")
            reasons.append(f"{dmin:.0f} km from the nearest valid public record (threshold {range_km:.0f} km).")
        elevs = [k["elevation_m"] for k in known if k.get("elevation_m") is not None]
        if altitude_m is not None and len(elevs) >= 5:
            lo, hi = float(np.percentile(elevs, 2.5)), float(np.percentile(elevs, 97.5))
            facts["known_elevation_range_m"] = [round(lo), round(hi)]
            if altitude_m < lo - ELEV_MARGIN_M or altitude_m > hi + ELEV_MARGIN_M:
                flags.append("UNUSUAL OBSERVATION")
                reasons.append(f"Altitude {altitude_m:.0f} m is outside the known range {lo:.0f}–{hi:.0f} m "
                               f"(±{ELEV_MARGIN_M:.0f} m).")
    else:
        reasons.append("No valid public records of this taxon to compare with.")
    if not known:
        flags.append("REQUIRES TAXONOMIC REVIEW")
    if len(known) < 10:
        facts["rare_in_public_data"] = True
        reasons.append(f"Few public records ({len(known)}): the taxon is rare or poorly sampled in public data.")
    if model:
        s = _suitability_at(model["grid"], lat, lon)
        facts["environmental_suitability"] = None if s is None else round(s, 3)
        facts["model_threshold_p10"] = model.get("threshold")
        facts["model_run_id"] = model.get("run_id")
        if s is None:
            reasons.append("The observation is outside the modelled extent.")
        elif model.get("threshold") is not None and s < model["threshold"]:
            flags.append("UNUSUAL OBSERVATION")
            reasons.append(f"Environmental suitability {s:.2f} is below the model's 10th-percentile training "
                           f"threshold ({model['threshold']:.2f}): atypical conditions for known records.")
    else:
        reasons.append("No completed distribution model for this taxon; environmental check skipped.")
    flags = list(dict.fromkeys(f for f in flags if f))
    suggested = None
    if "POTENTIAL RANGE EXTENSION" in flags:
        suggested = "range_extension"
    elif "UNUSUAL OBSERVATION" in flags:
        suggested = "rare_observation"
    return {"flags": flags, "reasons": reasons, "facts": facts, "suggested_discovery_category": suggested,
            "provenance": "MODEL OUTPUT", "disclaimer": DISCLAIMER}
