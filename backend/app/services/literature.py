"""LiteratureProvider: published works that mention a taxon (for COMPARE SPECIES and the species page).

Sources (public, no key):
- GBIF literature index  GET https://api.gbif.org/v1/literature/search?gbifTaxonKey=…|q=…
  (peer-reviewed works citing GBIF-mediated data; https://www.gbif.org/developer/literature)
- Crossref               GET https://api.crossref.org/works?query.bibliographic=…&rows=…
  (bibliographic search; results are text matches, not curated taxonomic literature)
Results are pointers for the user to read — BIOQUEST never summarises or interprets them.
"""
from __future__ import annotations

from ..config import get_settings
from .http import ThrottledClient, UpstreamError


class LiteratureProvider:
    def __init__(self):
        s = get_settings()
        self.gbif = ThrottledClient("GBIF literature", s.gbif_api_base, 0.2)
        self.crossref = ThrottledClient("Crossref", s.crossref_api_base, 0.2)

    async def gbif_literature(self, name: str, gbif_key: str | None, limit: int = 5) -> list[dict]:
        params = {"limit": limit}
        if gbif_key:
            params["gbifTaxonKey"] = gbif_key
        else:
            params["q"] = f'"{name}"'
        data = await self.gbif.get("literature/search", **params)
        out = []
        for w in data.get("results", []):
            doi = (w.get("identifiers") or {}).get("doi")
            out.append({"title": w.get("title"), "year": w.get("year"),
                        "authors": ", ".join(f"{a.get('lastName', '')}" for a in (w.get("authors") or [])[:3]),
                        "venue": w.get("source"), "doi": doi,
                        "url": f"https://doi.org/{doi}" if doi else (w.get("websites") or [None])[0],
                        "source": "GBIF literature index"})
        return out

    async def crossref_works(self, name: str, limit: int = 5) -> list[dict]:
        s = get_settings()
        data = await self.crossref.get("works", **{"query.bibliographic": name, "rows": limit,
                                                    "select": "DOI,title,author,issued,container-title",
                                                    "mailto": s.contact_email or None})
        out = []
        for w in (data.get("message") or {}).get("items", []):
            parts = ((w.get("issued") or {}).get("date-parts") or [[None]])[0]
            out.append({"title": (w.get("title") or [""])[0], "year": parts[0] if parts else None,
                        "authors": ", ".join(a.get("family", "") for a in (w.get("author") or [])[:3]),
                        "venue": (w.get("container-title") or [None])[0], "doi": w.get("DOI"),
                        "url": f"https://doi.org/{w['DOI']}" if w.get("DOI") else None,
                        "source": "Crossref (text match)"})
        return out

    async def search(self, name: str, gbif_key: str | None = None, limit: int = 5) -> dict:
        errors, items = [], []
        for fn in (lambda: self.gbif_literature(name, gbif_key, limit), lambda: self.crossref_works(name, limit)):
            try:
                items += await fn()
            except UpstreamError as e:
                errors.append({"service": e.service, "detail": e.detail})
        seen, uniq = set(), []
        for it in items:
            k = (it.get("doi") or it.get("title") or "").lower()
            if k and k not in seen:
                seen.add(k)
                uniq.append(it)
        return {"status": "ok" if uniq or not errors else "error", "items": uniq, "errors": errors,
                "provenance": "LIVE DATA", "query": name,
                "note": "Pointers to published works; read them before drawing conclusions. Crossref hits are "
                        "text matches and may be off-topic."}


_lit: LiteratureProvider | None = None


def get_literature() -> LiteratureProvider:
    global _lit
    if _lit is None:
        _lit = LiteratureProvider()
    return _lit
