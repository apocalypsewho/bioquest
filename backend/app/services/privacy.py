"""Coordinate privacy: public / approximate / private, and generalisation of sensitive taxa.

Rules
- User locations are never returned to other users; a user's own exact location stays client-side.
- Observations default to "approximate" (snapped to a 0.1° ≈ 11 km grid cell centre).
- Sensitive taxa (threatened / iNaturalist-obscured) are generalised to 0.2° for everyone except
  the record owner, mirroring iNaturalist's 0.2° obscuration cell.
- "private" records are never exposed with coordinates outside the owner's own views.
"""
from __future__ import annotations

import math

APPROX_DEG = 0.1
SENSITIVE_DEG = 0.2


def snap(lat: float, lon: float, cell: float) -> tuple[float, float]:
    return (math.floor(lat / cell) * cell + cell / 2, math.floor(lon / cell) * cell + cell / 2)


def public_coords(lat, lon, privacy: str, sensitive: bool = False, is_owner: bool = False):
    """Coordinates safe to show to the requester, plus the applied generalisation."""
    if lat is None or lon is None:
        return None, None, "none"
    if is_owner:
        return lat, lon, "exact (owner)"
    if privacy == "private":
        return None, None, "hidden"
    if sensitive:
        la, lo = snap(lat, lon, SENSITIVE_DEG)
        return la, lo, f"generalised {SENSITIVE_DEG}° (sensitive taxon)"
    if privacy == "approximate":
        la, lo = snap(lat, lon, APPROX_DEG)
        return la, lo, f"generalised {APPROX_DEG}°"
    return lat, lon, "exact (public)"


def generalise_occurrence(rec: dict, sensitive: bool) -> dict:
    """Generalise an external occurrence before sending it to the map, if the taxon is sensitive."""
    if sensitive and rec.get("lat") is not None and not rec.get("coordinates_obscured"):
        rec["lat"], rec["lon"] = snap(rec["lat"], rec["lon"], SENSITIVE_DEG)
        rec["coordinate_generalisation"] = f"{SENSITIVE_DEG}° (sensitive taxon)"
    return rec
