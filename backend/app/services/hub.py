"""BiodiversityHub: one entry point that merges sources and keeps provenance explicit.

mode = "live" → iNaturalist + GBIF (real APIs, LIVE DATA). Errors are surfaced, never replaced by demo data.
mode = "demo" → DemoDataProvider only (DEMO DATA).
"""
from __future__ import annotations

import asyncio

from .demo import DemoDataProvider
from .gbif import GBIFService
from .http import UpstreamError
from .inaturalist import INaturalistService
from .types import DEMO, LIVE, OccurrenceRecord, TaxonRecord

inat = INaturalistService()
gbif = GBIFService()
demo = DemoDataProvider()


async def _safe(coro, errors: list, service: str):
    try:
        return await coro
    except UpstreamError as e:
        errors.append({"service": service, "detail": e.detail})
        return None


async def search_taxa(q: str, mode: str) -> dict:
    if mode == "demo":
        return {"provenance": DEMO, "results": [t.to_dict() for t in demo.search_taxa(q)], "errors": []}
    errors: list = []
    i, g = await asyncio.gather(_safe(inat.search_taxa(q), errors, "iNaturalist"),
                                _safe(gbif.search_species(q), errors, "GBIF"))
    results = [t.to_dict() for t in (i or [])] + [t.to_dict() for t in (g or [])]
    return {"provenance": LIVE, "results": results, "errors": errors}


async def resolve_counterparts(key: str, mode: str) -> tuple[TaxonRecord | None, dict[str, str], list]:
    """Return the taxon plus its keys in every live source (matched by scientific name)."""
    errors: list = []
    if mode == "demo" or key.startswith("demo:"):
        t = demo.get_taxon(key)
        return t, ({"demo": t.key} if t else {}), errors
    src, sid = key.split(":", 1)
    keys = {src: key}
    if src == "inat":
        t = await _safe(inat.get_taxon(sid), errors, "iNaturalist")
        if t:
            m = await _safe(gbif.match(t.scientific_name), errors, "GBIF")
            if m and m.scientific_name.lower() == t.scientific_name.lower():
                keys["gbif"] = m.key
    else:
        t = await _safe(gbif.get_species(sid), errors, "GBIF")
        if t:
            cand = await _safe(inat.search_taxa(t.scientific_name, 5), errors, "iNaturalist") or []
            exact = [c for c in cand if c.scientific_name.lower() == t.scientific_name.lower()]
            if exact:
                keys["inat"] = exact[0].key
                t.photo_url = t.photo_url or exact[0].photo_url
                t.photo_attribution = t.photo_attribution or exact[0].photo_attribution
                t.common_name = t.common_name or exact[0].common_name
                t.is_sensitive = t.is_sensitive or exact[0].is_sensitive
    return t, keys, errors


async def occurrences(key: str, mode: str, max_per_source: int = 900) -> dict:
    t, keys, errors = await resolve_counterparts(key, mode)
    if not t:
        return {"taxon": None, "keys": keys, "records": [], "errors": errors or [{"service": "BIOQUEST",
                                                                                   "detail": "taxon not found"}]}
    recs: list[OccurrenceRecord] = []
    info = {}
    if "demo" in keys:
        recs = demo.occurrences(keys["demo"])
        info["demo"] = {"fetched": len(recs), "total": len(recs)}
        return {"taxon": t, "keys": keys, "records": recs, "errors": errors, "source_info": info, "provenance": DEMO}
    tasks = {}
    if "inat" in keys:
        tasks["inat"] = _safe(inat.observations(keys["inat"].split(":")[1], max_records=max_per_source), errors,
                              "iNaturalist")
    if "gbif" in keys:
        tasks["gbif"] = _safe(gbif.occurrences(keys["gbif"].split(":")[1], max_records=max_per_source), errors, "GBIF")
    done = dict(zip(tasks, await asyncio.gather(*tasks.values())))
    if done.get("inat"):
        r, total = done["inat"]
        recs += r
        info["inaturalist"] = {"fetched": len(r), "total_georeferenced": total,
                               "truncated": total > len(r)}
    if done.get("gbif"):
        r, total, no_coord = done["gbif"]
        recs += r
        info["gbif"] = {"fetched": len(r), "total_with_coordinates": total, "without_coordinates": no_coord,
                        "truncated": total > len(r), "note": gbif.download_note if total > len(r) else None}
    return {"taxon": t, "keys": keys, "records": recs, "errors": errors, "source_info": info, "provenance": LIVE}


async def effort_records(bbox, mode: str, max_records: int = 1000) -> dict:
    """All-taxa observations in a bbox, used as a sample of sampling effort."""
    if mode == "demo":
        return {"records": demo.effort_records(bbox), "provenance": DEMO, "errors": [], "complete": True,
                "note": "DEMO effort data (fictitious)."}
    errors: list = []
    res = await _safe(inat.observations(None, bbox=bbox, max_records=max_records, newest_first=True), errors, "iNaturalist")
    g = await _safe(gbif.count_in_bbox(bbox), errors, "GBIF")
    records = []
    total = 0
    if res:
        obs, total = res
        records = [{"lat": o.lat, "lon": o.lon, "observer": o.recorded_by, "taxon": o.scientific_name,
                    "rank": o.taxon_rank, "year": o.year} for o in obs if o.lat is not None]
    complete = total <= len(records)
    return {
        "records": records, "provenance": LIVE, "errors": errors, "complete": complete,
        "inat_total_in_area": total, "gbif_total_in_area": g,
        "note": ("Effort estimated from all iNaturalist observations in the area."
                 if complete else f"Effort estimated from a sample of {len(records)} of {total} iNaturalist "
                                  "observations (most recent first); relative patterns only."),
    }


async def target_group_points(key: str, mode: str, bbox, max_records: int = 3000) -> dict:
    """Records of a related group in the study extent, used for target-group (bias-corrected) background.

    LIVE: GBIF occurrences of the target's family (falls back to order, then class) inside the bbox.
    DEMO: the fictitious all-taxa effort records.
    """
    if mode == "demo":
        pts = [(r["lat"], r["lon"]) for r in demo.effort_records(bbox)]
        return {"points": pts, "source": "DEMO all-taxa effort records (fictitious)", "errors": []}
    errors: list = []
    _, keys, errs = await resolve_counterparts(key, mode)
    errors += errs
    if "gbif" not in keys:
        return {"points": [], "source": "", "errors": errors + [{"service": "GBIF",
                                                                  "detail": "no GBIF counterpart for the taxon"}]}
    sp = await _safe(gbif.get_species(keys["gbif"].split(":")[1]), errors, "GBIF")
    if not sp:
        return {"points": [], "source": "", "errors": errors}
    for rank in ("family", "order", "class"):
        hk = sp.extra.get(f"{rank}_key")
        if not hk:
            continue
        res = await _safe(gbif.occurrences(str(hk), bbox=tuple(bbox), max_records=max_records), errors, "GBIF")
        if res and len(res[0]) >= 50:
            recs, total, _ = res
            label = sp.classification.get(rank, hk)
            return {"points": [(r.lat, r.lon) for r in recs if r.lat is not None],
                    "source": f"GBIF records of {rank} {label} in the extent ({len(recs)} of {total})",
                    "errors": errors}
    return {"points": [], "source": "", "errors": errors}
