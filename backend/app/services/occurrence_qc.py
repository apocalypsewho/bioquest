"""Occurrence quality-control pipeline.

Every record ends with qc_status VALID / QUESTIONABLE / EXCLUDED and the list of reasons.
Nothing is deleted: EXCLUDED records stay visible (greyed) in the UI and in exports.

Checks are inspired by CoordinateCleaner (Zizka et al. 2019, Methods Ecol Evol 10:744) and
GBIF interpretation flags (https://gbif.github.io/gbif-api/apidocs/org/gbif/api/vocabulary/OccurrenceIssue.html).
Country check: offline reverse geocoding with `reverse_geocoder` (GeoNames cities ≥1000 inhabitants, bundled
with the package): each record gets the country of its nearest GeoNames place. This fills the country of
records that have none (e.g. iNaturalist) and flags a mismatch with the reported country as QUESTIONABLE
(nearest-place is not a border polygon, so it can be wrong close to borders; never EXCLUDED on this alone).
Country-centroid, capital, institution and sea/land tests need reference layers that are NOT bundled;
they are reported as "not run" in the summary.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .geo import haversine_km
from .types import OccurrenceRecord

ORDER = {"VALID": 0, "QUESTIONABLE": 1, "EXCLUDED": 2}
RANK_LEVEL = {"kingdom": 0, "phylum": 1, "class": 2, "order": 3, "family": 4, "genus": 5, "species": 6,
              "subspecies": 7, "variety": 7, "form": 7, "hybrid": 6, "complex": 5.5, "section": 5.5}

GBIF_EXCLUDE = {
    "ZERO_COORDINATE": "GBIF flag ZERO_COORDINATE",
    "COORDINATE_INVALID": "GBIF flag COORDINATE_INVALID",
    "COORDINATE_OUT_OF_RANGE": "GBIF flag COORDINATE_OUT_OF_RANGE",
    "COUNTRY_COORDINATE_MISMATCH": "coordinates fall outside the reported country (GBIF flag)",
}
GBIF_QUESTION = {
    "PRESUMED_SWAPPED_COORDINATE": "GBIF had to swap lat/lon (presumed error)",
    "PRESUMED_NEGATED_LATITUDE": "GBIF negated latitude (presumed error)",
    "PRESUMED_NEGATED_LONGITUDE": "GBIF negated longitude (presumed error)",
    "TAXON_MATCH_FUZZY": "fuzzy taxonomic name match (GBIF)",
    "TAXON_MATCH_HIGHERRANK": "name only matched at a higher rank (GBIF)",
    "COORDINATE_REPROJECTION_FAILED": "coordinate reprojection failed (GBIF)",
}


@dataclass
class QCConfig:
    # Target taxon per source prefix, e.g. {"inat": "inat:48662", "gbif": "gbif:2435099"}
    target_keys: dict[str, str] = field(default_factory=dict)
    target_rank: Optional[str] = None
    expected_countries: list[str] = field(default_factory=list)  # ISO-2; empty = not checked
    max_uncertainty_m: float = 10_000  # > → EXCLUDED
    warn_uncertainty_m: float = 2_000  # > → QUESTIONABLE
    min_decimals: int = 2
    outlier_multiplier: float = 5.0
    outlier_min_records: int = 7
    thin_res_deg: Optional[float] = None
    country_check: bool = True


def _decimals(x: float) -> int:
    s = repr(float(x))
    if "e" in s:
        return 6
    return len(s.split(".")[1].rstrip("0")) if "." in s else 0


def _flag(rec: OccurrenceRecord, status: str, reason: str):
    if ORDER[status] > ORDER[rec.qc_status]:
        rec.qc_status = status
    if reason not in rec.qc_reasons:
        rec.qc_reasons.append(f"[{status}] {reason}")


def run_qc(records: list[OccurrenceRecord], cfg: QCConfig) -> dict:
    today = dt.date.today().isoformat()
    for r in records:
        r.qc_status, r.qc_reasons, r.duplicate_of, r.thinned = "VALID", [], None, False

        # --- coordinates ---
        if r.lat is None or r.lon is None:
            _flag(r, "EXCLUDED", "missing coordinates")
            continue
        if not (-90 <= r.lat <= 90 and -180 <= r.lon <= 180):
            _flag(r, "EXCLUDED", "impossible coordinates (out of range)")
            continue
        if r.lat == 0 and r.lon == 0:
            _flag(r, "EXCLUDED", "coordinates 0,0")
        elif r.lat == 0 or r.lon == 0:
            _flag(r, "QUESTIONABLE", "latitude or longitude exactly 0")
        if r.lat == r.lon:
            _flag(r, "QUESTIONABLE", "latitude equals longitude (possible data-entry error)")
        dec = min(_decimals(r.lat), _decimals(r.lon))
        if dec == 0:
            _flag(r, "EXCLUDED", "integer-degree coordinates (very low precision)")
        elif dec < cfg.min_decimals:
            _flag(r, "QUESTIONABLE", f"low coordinate precision ({dec} decimal place)")
        for issue in r.issues:
            if issue in GBIF_EXCLUDE:
                _flag(r, "EXCLUDED", GBIF_EXCLUDE[issue])
            elif issue in GBIF_QUESTION:
                _flag(r, "QUESTIONABLE", GBIF_QUESTION[issue])
        if r.uncertainty_m is not None:
            if r.uncertainty_m > cfg.max_uncertainty_m:
                _flag(r, "EXCLUDED", f"coordinate uncertainty {r.uncertainty_m:.0f} m > {cfg.max_uncertainty_m:.0f} m")
            elif r.uncertainty_m > cfg.warn_uncertainty_m:
                _flag(r, "QUESTIONABLE", f"coordinate uncertainty {r.uncertainty_m:.0f} m")
        if r.coordinates_obscured:
            _flag(r, "QUESTIONABLE", "coordinates obscured by source (~0.2° cell); unsuitable for fine-scale models")

        # --- record nature ---
        if r.captive_or_cultivated:
            _flag(r, "EXCLUDED", "captive / cultivated / living specimen")
        if r.basis_of_record == "FOSSIL_SPECIMEN":
            _flag(r, "EXCLUDED", "fossil specimen")
        if r.event_date and r.event_date[:10] > today:
            _flag(r, "QUESTIONABLE", "event date in the future")

        # --- identification / taxonomy ---
        if r.quality_grade == "casual":
            _flag(r, "EXCLUDED", "iNaturalist 'casual' grade (missing evidence/date/location, or captive)")
        elif r.quality_grade == "needs_id":
            _flag(r, "QUESTIONABLE", "identification not yet community-supported (iNaturalist 'needs ID')")
        tk = cfg.target_keys.get(r.source_prefix)
        if tk and r.taxon_ancestor_keys:
            if tk not in r.taxon_ancestor_keys:
                _flag(r, "EXCLUDED", f"record taxon '{r.scientific_name}' is not within the target taxon")
        if cfg.target_rank and r.taxon_rank:
            if RANK_LEVEL.get(r.taxon_rank, 9) < RANK_LEVEL.get(cfg.target_rank, 0):
                _flag(r, "QUESTIONABLE", f"identified only to {r.taxon_rank}")

    summary_notes = ["country-centroid, capital, institution and sea/land tests not run (gazetteer layers not bundled)"]
    summary_notes.append(_country_check(records) if cfg.country_check else "country check disabled")
    if cfg.expected_countries:
        exp = {c.upper() for c in cfg.expected_countries}
        for r in records:
            cc = r.country_code or r.derived_country_code
            if r.lat is not None and cc and cc.upper() not in exp:
                _flag(r, "QUESTIONABLE", f"outside expected countries ({cc})")
    else:
        summary_notes.append("expected-country check not run (no expected countries set)")

    _mark_duplicates(records)
    _mark_outliers(records, cfg)
    if cfg.thin_res_deg:
        _thin(records, cfg.thin_res_deg)
    return summarise(records, summary_notes)


def _country_check(records: list[OccurrenceRecord]) -> str:
    pts = [r for r in records if r.lat is not None and r.lon is not None and r.qc_status != "EXCLUDED"]
    if not pts:
        return "country check: no records with coordinates"
    try:
        import reverse_geocoder as rg
    except ImportError:
        return "country check not run (reverse_geocoder not installed)"
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        hits = rg.search([(r.lat, r.lon) for r in pts], mode=1)
    mism = filled = 0
    for r, h in zip(pts, hits):
        r.derived_country_code = h.get("cc") or None
        if not r.derived_country_code:
            continue
        if not r.country_code:
            filled += 1
        elif r.country_code.upper() != r.derived_country_code.upper():
            mism += 1
            _flag(r, "QUESTIONABLE", f"reported country {r.country_code} but nearest GeoNames place is in "
                                     f"{r.derived_country_code} (offline check; can be wrong near borders)")
    return (f"country check (offline, nearest GeoNames place): {len(pts)} records checked, {filled} without "
            f"reported country assigned one, {mism} mismatches flagged")


def _mark_duplicates(records: list[OccurrenceRecord]):
    # 1) Cross-source: GBIF mirrors iNaturalist research-grade observations.
    inat_ids = {r.source_record_id: r.uid for r in records if r.source == "inaturalist"}
    for r in records:
        if r.source == "gbif" and r.inat_observation_id and r.inat_observation_id in inat_ids:
            r.duplicate_of = inat_ids[r.inat_observation_id]
            _flag(r, "EXCLUDED", f"duplicate of {r.duplicate_of} (same iNaturalist observation shared via GBIF)")
    # 2) Same coordinates (≈11 m) + same date, any source.
    seen: dict[tuple, str] = {}
    for r in sorted(records, key=lambda x: ORDER[x.qc_status]):
        if r.lat is None or r.duplicate_of or r.qc_status == "EXCLUDED":
            continue
        k = (round(r.lat, 4), round(r.lon, 4), (r.event_date or "")[:10])
        if k in seen:
            r.duplicate_of = seen[k]
            _flag(r, "EXCLUDED", f"duplicate of {seen[k]} (same coordinates and date)")
        else:
            seen[k] = r.uid


def _mark_outliers(records: list[OccurrenceRecord], cfg: QCConfig):
    pool = [r for r in records if r.qc_status != "EXCLUDED" and r.lat is not None]
    if len(pool) < cfg.outlier_min_records:
        return
    lat = np.array([r.lat for r in pool])
    lon = np.array([r.lon for r in pool])
    d = haversine_km(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
    mean_d = d.sum(1) / (len(pool) - 1)
    q1, q3 = np.percentile(mean_d, [25, 75])
    lim = q3 + cfg.outlier_multiplier * (q3 - q1)
    for r, m in zip(pool, mean_d):
        if m > lim and m > 100:  # ignore tight clusters where IQR≈0
            _flag(r, "QUESTIONABLE",
                  f"geographic outlier (mean distance {m:.0f} km > {lim:.0f} km): data error OR genuine range "
                  "extension — needs review, not removed")


def _thin(records: list[OccurrenceRecord], res: float):
    taken = set()
    for r in sorted(records, key=lambda x: (ORDER[x.qc_status], x.uncertainty_m or 0)):
        if r.qc_status != "VALID":
            continue
        cell = (int(np.floor(r.lat / res)), int(np.floor(r.lon / res)))
        if cell in taken:
            r.thinned = True
        else:
            taken.add(cell)


def summarise(records: list[OccurrenceRecord], notes: list[str] | None = None) -> dict:
    counts = defaultdict(int)
    reasons = defaultdict(int)
    by_source = defaultdict(lambda: defaultdict(int))
    for r in records:
        counts[r.qc_status] += 1
        by_source[r.source][r.qc_status] += 1
        for reason in r.qc_reasons:
            reasons[reason.split("] ", 1)[-1].split(" (")[0]] += 1
    return {
        "total": len(records),
        "VALID": counts["VALID"],
        "QUESTIONABLE": counts["QUESTIONABLE"],
        "EXCLUDED": counts["EXCLUDED"],
        "thinned": sum(1 for r in records if r.thinned),
        "by_source": {k: dict(v) for k, v in by_source.items()},
        "reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
        "notes": notes or [],
    }
