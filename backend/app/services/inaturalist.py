"""INaturalistService: adapter for the public iNaturalist API v1.

Docs: https://api.inaturalist.org/v1/docs/  ·  API recommended practices:
https://www.inaturalist.org/pages/api+recommended+practices (≈1 req/s, ≤10k req/day, descriptive UA).
OAuth: https://www.inaturalist.org/pages/api+reference#auth

Only documented endpoints are used. Writing to iNaturalist (create observation / upload photo)
requires the user's OAuth authorization AND an explicit per-observation consent from the UI.
"""
from __future__ import annotations

from typing import Optional

from ..config import get_settings
from .http import ThrottledClient, UpstreamError
from .types import LIVE, OccurrenceRecord, TaxonRecord

RANKS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]


def _medium(url: Optional[str]) -> Optional[str]:
    return url.replace("/square.", "/medium.") if url else url


class INaturalistService:
    source = "inaturalist"

    def __init__(self):
        s = get_settings()
        self.s = s
        self.api = ThrottledClient("iNaturalist", s.inat_api_base, s.inat_min_interval_s)
        self.web = ThrottledClient("iNaturalist", s.inat_web_base, s.inat_min_interval_s)

    # ---------- taxa ----------
    def _taxon(self, t: dict) -> TaxonRecord:
        classification = {}
        for a in t.get("ancestors") or []:
            if a.get("rank") in RANKS:
                classification[a["rank"]] = a.get("name")
        if t.get("rank") in RANKS:
            classification[t["rank"]] = t.get("name")
        cs = t.get("conservation_status") or {}
        photo = t.get("default_photo") or {}
        return TaxonRecord(
            key=f"inat:{t['id']}",
            source=self.source,
            source_id=str(t["id"]),
            scientific_name=t.get("name", ""),
            rank=t.get("rank", ""),
            common_name=t.get("preferred_common_name"),
            classification=classification,
            observations_count=t.get("observations_count"),
            photo_url=photo.get("medium_url") or _medium(photo.get("url")),
            photo_attribution=photo.get("attribution"),
            conservation_status=cs.get("status_name") or cs.get("status"),
            # iNaturalist obscures coordinates of taxa whose status geoprivacy is obscured/private
            is_sensitive=bool(cs) and cs.get("geoprivacy") in ("obscured", "private"),
            url=f"{self.s.inat_web_base}/taxa/{t['id']}",
            provenance=LIVE,
            extra={"ancestor_ids": t.get("ancestor_ids", []), "iconic_taxon_name": t.get("iconic_taxon_name")},
        )

    async def search_taxa(self, q: str, limit: int = 10) -> list[TaxonRecord]:
        data = await self.api.get("taxa/autocomplete", q=q, per_page=limit)
        return [self._taxon(t) for t in data.get("results", [])]

    async def get_taxon(self, taxon_id: str) -> TaxonRecord:
        data = await self.api.get(f"taxa/{taxon_id}")
        res = data.get("results") or []
        if not res:
            raise UpstreamError("iNaturalist", f"taxon {taxon_id} not found")
        return self._taxon(res[0])

    # ---------- observations ----------
    def _occurrence(self, o: dict, target_key: str) -> OccurrenceRecord:
        lat = lon = None
        gj = o.get("geojson") or {}
        if gj.get("type") == "Point" and gj.get("coordinates"):
            lon, lat = gj["coordinates"][0], gj["coordinates"][1]
        taxon = o.get("taxon") or {}
        photos = o.get("photos") or []
        details = o.get("observed_on_details") or {}
        return OccurrenceRecord(
            source=self.source,
            source_record_id=str(o["id"]),
            scientific_name=taxon.get("name", ""),
            taxon_key=target_key,
            lat=lat,
            lon=lon,
            uncertainty_m=o.get("public_positional_accuracy") or o.get("positional_accuracy"),
            event_date=o.get("observed_on"),
            year=details.get("year"),
            basis_of_record="HUMAN_OBSERVATION",
            institution="iNaturalist",
            recorded_by=(o.get("user") or {}).get("login"),
            url=o.get("uri") or f"{self.s.inat_web_base}/observations/{o['id']}",
            photo_url=_medium(photos[0].get("url")) if photos else None,
            quality_grade=o.get("quality_grade"),
            taxon_rank=taxon.get("rank"),
            taxon_ancestor_keys=[f"inat:{a}" for a in (taxon.get("ancestor_ids") or [])]
            + ([f"inat:{taxon['id']}"] if taxon.get("id") else []),
            captive_or_cultivated=o.get("captive"),
            coordinates_obscured=bool(o.get("obscured")) or o.get("geoprivacy") in ("obscured", "private")
            or o.get("taxon_geoprivacy") in ("obscured", "private"),
            inat_observation_id=str(o["id"]),
            provenance=LIVE,
        )

    async def observations(
        self,
        taxon_id: Optional[str] = None,
        *,
        bbox: Optional[tuple[float, float, float, float]] = None,  # (minlon, minlat, maxlon, maxlat)
        d1: Optional[str] = None,
        d2: Optional[str] = None,
        quality_grade: Optional[str] = None,
        max_records: int = 600,
        newest_first: bool = False,
    ) -> tuple[list[OccurrenceRecord], int]:
        """Georeferenced observations. Uses id_above paging (recommended for deep result sets)."""
        params = {
            "taxon_id": taxon_id,
            "geo": "true",
            "per_page": 200,
            "order_by": "id",
            "order": "desc" if newest_first else "asc",
            "d1": d1,
            "d2": d2,
            "quality_grade": quality_grade,
        }
        if bbox:
            params.update(swlng=bbox[0], swlat=bbox[1], nelng=bbox[2], nelat=bbox[3])
        out: list[OccurrenceRecord] = []
        total = 0
        cursor = None
        cursor_key = "id_below" if newest_first else "id_above"
        while len(out) < max_records:
            data = await self.api.get("observations", **params, **{cursor_key: cursor})
            total = data.get("total_results", 0)
            results = data.get("results", [])
            if not results:
                break
            key = f"inat:{taxon_id}" if taxon_id else "inat:any"
            out.extend(self._occurrence(o, key) for o in results)
            cursor = results[-1]["id"]
            if len(results) < 200:
                break
        return out[:max_records], total

    async def count(self, **params) -> int:
        data = await self.api.get("observations", per_page=0, **params)
        return int(data.get("total_results", 0))

    async def species_counts(self, bbox, per_page: int = 500) -> tuple[list[dict], int]:
        data = await self.api.get(
            "observations/species_counts",
            swlng=bbox[0], swlat=bbox[1], nelng=bbox[2], nelat=bbox[3], verifiable="true", per_page=per_page,
        )
        return data.get("results", []), int(data.get("total_results", 0))

    async def observer_count(self, bbox) -> int:
        data = await self.api.get(
            "observations/observers", swlng=bbox[0], swlat=bbox[1], nelng=bbox[2], nelat=bbox[3], per_page=1
        )
        return int(data.get("total_results", 0))

    # ---------- OAuth + write ----------
    def authorize_url(self, state: str) -> str:
        from urllib.parse import urlencode

        if not self.s.inat_client_id:
            raise UpstreamError("iNaturalist", "OAuth not configured (set BIOQUEST_INAT_CLIENT_ID/SECRET)")
        q = urlencode(
            {"client_id": self.s.inat_client_id, "redirect_uri": self.s.inat_redirect_uri,
             "response_type": "code", "state": state}
        )
        return f"{self.s.inat_web_base}/oauth/authorize?{q}"

    async def exchange_code(self, code: str) -> str:
        data = await self.web.request(
            "POST", "oauth/token",
            data={"client_id": self.s.inat_client_id, "client_secret": self.s.inat_client_secret, "code": code,
                  "redirect_uri": self.s.inat_redirect_uri, "grant_type": "authorization_code"},
        )
        return data["access_token"]

    async def api_jwt(self, access_token: str) -> str:
        """Exchange the OAuth access token for a short-lived (24h) API JWT."""
        data = await self.web.request("GET", "users/api_token", headers={"Authorization": f"Bearer {access_token}"})
        return data["api_token"]

    async def me(self, jwt: str) -> dict:
        data = await self.api.request("GET", "users/me", headers={"Authorization": jwt})
        return (data.get("results") or [{}])[0]

    async def observation(self, observation_id: int) -> dict:
        """Public view of one observation (quality_grade, community taxon)."""
        data = await self.api.get(f"observations/{observation_id}")
        res = data.get("results") or []
        if not res:
            raise UpstreamError("iNaturalist", f"observation {observation_id} not found")
        return res[0]

    async def create_observation(self, jwt: str, payload: dict) -> dict:
        return await self.api.request("POST", "observations", json={"observation": payload},
                                      headers={"Authorization": jwt})

    async def upload_photo(self, jwt: str, observation_id: int, filename: str, content: bytes, content_type: str):
        return await self.api.request(
            "POST", "observation_photos",
            data={"observation_photo[observation_id]": str(observation_id)},
            files={"file": (filename, content, content_type)},
            headers={"Authorization": jwt},
        )
