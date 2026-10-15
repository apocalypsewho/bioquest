"""GBIFService: adapter for the GBIF REST API v1.

Docs: https://techdocs.gbif.org/en/openapi/  (species: /v1/species, occurrences: /v1/occurrence/search)
Search API is unauthenticated; paging is capped at 300 records/page and offset+limit <= 100,000.
For larger, citable extracts use the GBIF download API (requires a GBIF account) — see
`GBIFService.download_note`.

Data use: every record must be cited via its dataset (https://www.gbif.org/terms).
"""
from __future__ import annotations

from typing import Optional

from ..config import get_settings
from .http import ThrottledClient
from .types import LIVE, OccurrenceRecord, TaxonRecord

INAT_RESEARCH_GRADE_DATASET = "50c9509d-22c7-4a22-a47d-8c48425ef4a7"
RANKS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]


class GBIFService:
    source = "gbif"
    download_note = (
        "For >100k records or formal publication use the GBIF occurrence download API "
        "(POST /v1/occurrence/download/request, requires GBIF credentials) to obtain a DOI."
    )

    def __init__(self):
        self.client = ThrottledClient("GBIF", get_settings().gbif_api_base, 0.2)

    def _taxon(self, t: dict) -> TaxonRecord:
        key = t.get("key") or t.get("usageKey")
        return TaxonRecord(
            key=f"gbif:{key}",
            source=self.source,
            source_id=str(key),
            scientific_name=t.get("canonicalName") or t.get("scientificName", ""),
            rank=(t.get("rank") or "").lower(),
            common_name=t.get("vernacularName"),
            classification={r: t[r] for r in RANKS if t.get(r)},
            url=f"https://www.gbif.org/species/{key}",
            provenance=LIVE,
            extra={"authorship": t.get("authorship"), "taxonomic_status": t.get("taxonomicStatus") or t.get("status"),
                   **{f"{r}_key": t[f"{r}Key"] for r in ("family", "order", "class") if t.get(f"{r}Key")}},
        )

    async def search_species(self, q: str, limit: int = 10) -> list[TaxonRecord]:
        data = await self.client.get("species/suggest", q=q, limit=limit)
        return [self._taxon(t) for t in data]

    async def match(self, name: str) -> Optional[TaxonRecord]:
        data = await self.client.get("species/match", name=name)
        if not data.get("usageKey") or data.get("matchType") == "NONE":
            return None
        rec = self._taxon(data)
        rec.extra.update(match_type=data.get("matchType"), confidence=data.get("confidence"))
        return rec

    async def get_species(self, key: str) -> TaxonRecord:
        return self._taxon(await self.client.get(f"species/{key}"))

    def _occurrence(self, o: dict, target_key: str) -> OccurrenceRecord:
        inat_id = None
        if o.get("datasetKey") == INAT_RESEARCH_GRADE_DATASET:
            inat_id = str(o.get("catalogNumber") or "") or None
        return OccurrenceRecord(
            source=self.source,
            source_record_id=str(o["key"]),
            scientific_name=o.get("species") or o.get("scientificName", ""),
            taxon_key=target_key,
            lat=o.get("decimalLatitude"),
            lon=o.get("decimalLongitude"),
            uncertainty_m=o.get("coordinateUncertaintyInMeters"),
            event_date=(o.get("eventDate") or "")[:10] or None,
            year=o.get("year"),
            basis_of_record=o.get("basisOfRecord"),
            institution=o.get("institutionCode") or o.get("publishingOrgKey"),
            dataset=o.get("datasetKey"),
            recorded_by=o.get("recordedBy"),
            country_code=o.get("countryCode"),
            url=f"https://www.gbif.org/occurrence/{o['key']}",
            taxon_rank=(o.get("taxonRank") or "").lower() or None,
            taxon_ancestor_keys=[f"gbif:{o[k]}" for k in
                                 ("kingdomKey", "phylumKey", "classKey", "orderKey", "familyKey", "genusKey", "speciesKey",
                                  "taxonKey", "acceptedTaxonKey")
                                 if o.get(k)],
            captive_or_cultivated=((o.get("establishmentMeans") or "").upper() in ("MANAGED", "CULTIVATED", "CAPTIVE")
                                   or o.get("basisOfRecord") == "LIVING_SPECIMEN") or None,
            issues=o.get("issues") or [],
            references=o.get("references"),
            inat_observation_id=inat_id,
            provenance=LIVE,
        )

    async def occurrences(
        self,
        taxon_key: str,
        *,
        bbox: Optional[tuple[float, float, float, float]] = None,
        year: Optional[str] = None,  # "2000,2024"
        country: Optional[str] = None,
        max_records: int = 900,
    ) -> tuple[list[OccurrenceRecord], int, int]:
        """Returns (records with coordinates, total with coordinates, total WITHOUT coordinates)."""
        params = {"taxonKey": taxon_key, "hasCoordinate": "true", "limit": 300, "year": year, "country": country,
                  "occurrenceStatus": "PRESENT"}
        if bbox:
            params["decimalLongitude"] = f"{bbox[0]},{bbox[2]}"
            params["decimalLatitude"] = f"{bbox[1]},{bbox[3]}"
        out: list[OccurrenceRecord] = []
        offset, total = 0, 0
        while len(out) < max_records:
            data = await self.client.get("occurrence/search", **params, offset=offset)
            total = data.get("count", 0)
            res = data.get("results", [])
            out.extend(self._occurrence(o, f"gbif:{taxon_key}") for o in res)
            offset += len(res)
            if data.get("endOfRecords", True) or not res:
                break
        no_coord = (await self.client.get("occurrence/search", taxonKey=taxon_key, hasCoordinate="false", limit=0)).get(
            "count", 0)
        return out[:max_records], total, no_coord

    async def facets(self, taxon_key: str) -> dict:
        """Countries and year range for a taxon (exact counts from GBIF facets)."""
        data = await self.client.get(
            "occurrence/search", taxonKey=taxon_key, limit=0, facet=["country", "year"], facetLimit=300
        )
        out = {"total": data.get("count", 0), "countries": [], "years": []}
        for f in data.get("facets", []):
            if f["field"] == "COUNTRY":
                out["countries"] = [{"code": c["name"], "count": c["count"]} for c in f["counts"]]
            if f["field"] == "YEAR":
                out["years"] = sorted(int(c["name"]) for c in f["counts"])
        return out

    async def count_in_bbox(self, bbox) -> int:
        data = await self.client.get(
            "occurrence/search", limit=0, hasCoordinate="true",
            decimalLongitude=f"{bbox[0]},{bbox[2]}", decimalLatitude=f"{bbox[1]},{bbox[3]}",
        )
        return int(data.get("count", 0))
