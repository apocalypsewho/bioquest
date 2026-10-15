"""DEMO MODE data provider.

Everything produced here is FICTITIOUS and labelled "DEMO DATA": invented taxa (genus "Demoquestia",
which does not exist), invented occurrence points generated from the SYNTHETIC demo environment, and
invented background observations for sampling-effort maps. It exists only to let people try the
full workflow without API keys or network access. It must never be cited or exported as real data.
"""
from __future__ import annotations

import numpy as np

from .environment import DemoEnvironmentalProvider
from .geo import Grid
from .types import DEMO, OccurrenceRecord, TaxonRecord

DEMO_ORIGIN = {"lat": -11.95, "lon": -75.25, "label": "DEMO origin (fictitious field base)"}

_CLASSIF = {"kingdom": "Animalia", "phylum": "Arthropoda", "class": "Arachnida", "order": "Solifugae",
            "family": "Demoquestiidae (DEMO)"}

DEMO_TAXA = [
    TaxonRecord(key="demo:1", source="demo", source_id="1", scientific_name="Demoquestia andina", rank="species",
                common_name="Andean demo sun-spider (fictitious)",
                classification={**_CLASSIF, "genus": "Demoquestia", "species": "Demoquestia andina"},
                observations_count=74, provenance=DEMO,
                extra={"niche": {"elev": (3850, 350), "bio12": (700, 300)}, "n": 74, "seed": 11}),
    TaxonRecord(key="demo:2", source="demo", source_id="2", scientific_name="Demoquestia nebulosa", rank="species",
                common_name="Cloud-forest demo sun-spider (fictitious)",
                classification={**_CLASSIF, "genus": "Demoquestia", "species": "Demoquestia nebulosa"},
                observations_count=41, provenance=DEMO,
                extra={"niche": {"elev": (2700, 300), "bio12": (1100, 250)}, "n": 41, "seed": 12}),
    TaxonRecord(key="demo:3", source="demo", source_id="3", scientific_name="Demoquestia rara", rank="species",
                common_name="Rare demo sun-spider (fictitious)",
                classification={**_CLASSIF, "genus": "Demoquestia", "species": "Demoquestia rara"},
                observations_count=6, is_sensitive=True, conservation_status="DEMO: treated as sensitive",
                provenance=DEMO, extra={"niche": {"elev": (4300, 150), "bio12": (500, 120)}, "n": 6, "seed": 13}),
    TaxonRecord(key="demo:10", source="demo", source_id="10", scientific_name="Demoquestia", rank="genus",
                classification={**_CLASSIF, "genus": "Demoquestia"}, observations_count=121, provenance=DEMO,
                extra={"children": ["demo:1", "demo:2", "demo:3"]}),
]
_BY_KEY = {t.key: t for t in DEMO_TAXA}
REGION = [-76.6, -13.2, -73.9, -10.7]  # bbox for demo data generation


class DemoDataProvider:
    source = "demo"

    def __init__(self):
        self.env = DemoEnvironmentalProvider()

    def search_taxa(self, q: str) -> list[TaxonRecord]:
        q = (q or "").lower().strip()
        # Any query returns the fictitious taxa so the demo flow always works; names make the DEMO nature obvious.
        hits = [t for t in DEMO_TAXA if q and q in t.scientific_name.lower()]
        return hits or DEMO_TAXA

    def get_taxon(self, key: str) -> TaxonRecord | None:
        return _BY_KEY.get(key if key.startswith("demo:") else f"demo:{key}")

    def _suitability(self, grid: Grid, niche: dict) -> np.ndarray:
        env = self.env.grid(grid)
        s = np.ones_like(env["elev"])
        for var, (mu, sd) in niche.items():
            s *= np.exp(-0.5 * ((env[var] - mu) / sd) ** 2)
        return s

    def occurrences(self, key: str) -> list[OccurrenceRecord]:
        t = self.get_taxon(key)
        if not t:
            return []
        keys = t.extra.get("children") or [t.key]
        out: list[OccurrenceRecord] = []
        for k in keys:
            out.extend(self._species_occurrences(_BY_KEY[k]))
        return out

    def _species_occurrences(self, t: TaxonRecord) -> list[OccurrenceRecord]:
        rng = np.random.default_rng(t.extra["seed"])
        grid = Grid(REGION, 0.02)
        suit = self._suitability(grid, t.extra["niche"])
        # sampling bias: people sample near the (fictitious) road along lat ≈ -12 and near the field base
        LON, LAT = grid.centers()
        bias = 0.25 + np.exp(-((LAT + 12.0) / 0.25) ** 2) + np.exp(
            -(((LAT - DEMO_ORIGIN["lat"]) ** 2 + (LON - DEMO_ORIGIN["lon"]) ** 2) / 0.3 ** 2))
        w = (suit * bias).ravel()
        w /= w.sum()
        n = t.extra["n"]
        idx = rng.choice(w.size, n, replace=False, p=w)
        rows, cols = np.unravel_index(idx, suit.shape)
        recs = []
        for i, (r, c) in enumerate(zip(rows, cols)):
            lat = float(LAT[r, c] + rng.uniform(-0.009, 0.009))
            lon = float(LON[r, c] + rng.uniform(-0.009, 0.009))
            src_kind = "inaturalist-like" if i % 3 else "museum-like"
            recs.append(OccurrenceRecord(
                source="demo", source_record_id=f"{t.source_id}-{i}", scientific_name=t.scientific_name,
                taxon_key=t.key, lat=round(lat, 5), lon=round(lon, 5),
                uncertainty_m=float(rng.choice([15, 30, 100, 250, 1000])),
                event_date=f"{int(rng.integers(2008, 2026))}-{int(rng.integers(1, 13)):02d}-{int(rng.integers(1, 28)):02d}",
                basis_of_record="HUMAN_OBSERVATION" if src_kind == "inaturalist-like" else "PRESERVED_SPECIMEN",
                institution="DEMO collection" if src_kind == "museum-like" else "DEMO observers",
                recorded_by=f"demo_observer_{int(rng.integers(1, 15))}",
                country_code="PE", quality_grade="research", taxon_rank="species",
                taxon_ancestor_keys=[t.key, "demo:10"], provenance=DEMO,
            ))
            recs[-1].year = int(recs[-1].event_date[:4])
        # Deliberately problematic records so the QC pipeline has something to show
        if t.key == "demo:1":
            base = recs[0]
            bad = [
                dict(source_record_id="bad-zero", lat=0.0, lon=0.0),
                dict(source_record_id="bad-dup", lat=base.lat, lon=base.lon, event_date=base.event_date),
                dict(source_record_id="bad-uncert", lat=-12.31, lon=-75.02, uncertainty_m=25000),
                dict(source_record_id="bad-captive", lat=-12.07, lon=-75.21, captive_or_cultivated=True),
                dict(source_record_id="bad-needsid", lat=-11.71, lon=-75.48, quality_grade="needs_id"),
                dict(source_record_id="bad-outlier", lat=-3.2, lon=-60.1),
                dict(source_record_id="bad-precision", lat=-12.0, lon=-75.0),
                dict(source_record_id="bad-missing", lat=None, lon=None),
            ]
            for b in bad:
                rec = OccurrenceRecord(source="demo", scientific_name=t.scientific_name, taxon_key=t.key,
                                       uncertainty_m=b.pop("uncertainty_m", 30), event_date=b.pop("event_date", "2019-03-02"),
                                       basis_of_record="HUMAN_OBSERVATION", recorded_by="demo_observer_99",
                                       country_code="PE", quality_grade=b.pop("quality_grade", "research"),
                                       taxon_rank="species", taxon_ancestor_keys=[t.key, "demo:10"], provenance=DEMO, **b)
                recs.append(rec)
        return recs

    def effort_records(self, bbox) -> list[dict]:
        """Fictitious all-taxa observations used for the DEMO sampling-effort / richness map."""
        rng = np.random.default_rng(7)
        n = 2600
        # 60% along the road (lat ≈ -12), 25% around the field base, 15% scattered
        kinds = rng.choice(3, n, p=[0.6, 0.25, 0.15])
        lat = np.where(kinds == 0, rng.normal(-12.0, 0.04, n),
                       np.where(kinds == 1, rng.normal(DEMO_ORIGIN["lat"], 0.05, n), rng.uniform(REGION[1], REGION[3], n)))
        lon = np.where(kinds == 0, rng.uniform(REGION[0], REGION[2], n),
                       np.where(kinds == 1, rng.normal(DEMO_ORIGIN["lon"], 0.05, n), rng.uniform(REGION[0], REGION[2], n)))
        species = rng.zipf(1.6, n) % 400
        ranks = rng.choice(["species", "genus", "family"], n, p=[0.8, 0.15, 0.05])
        sel = (lon >= bbox[0]) & (lon <= bbox[2]) & (lat >= bbox[1]) & (lat <= bbox[3])
        return [
            {"lat": float(lat[i]), "lon": float(lon[i]), "observer": f"demo_observer_{int(rng.integers(1, 60))}",
             "taxon": f"DEMO taxon {int(species[i])}", "rank": str(ranks[i]), "year": int(rng.integers(2005, 2026))}
            for i in np.nonzero(sel)[0]
        ]

    def habitat(self, lat: float, lon: float) -> dict:
        g = Grid([lon - 0.01, lat - 0.01, lon + 0.01, lat + 0.01], 0.01)
        env = self.env.grid(g)
        elev = float(env["elev"].mean())
        p = float(env["bio12"].mean())
        if elev > 4200:
            hab = "high-Andean grassland (DEMO)"
        elif elev > 3400:
            hab = "montane scrub (DEMO)" if p < 900 else "humid montane grassland (DEMO)"
        elif elev > 2200:
            hab = "montane forest (DEMO)" if p > 900 else "dry inter-Andean valley (DEMO)"
        else:
            hab = "lowland forest (DEMO)"
        return {"elevation_m": round(elev), "habitat": hab, "source": "DEMO synthetic environment"}
