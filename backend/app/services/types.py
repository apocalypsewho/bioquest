"""Source-agnostic records shared by the iNaturalist, GBIF and DEMO adapters."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

LIVE = "LIVE DATA"
DEMO = "DEMO DATA"
MODEL = "MODEL OUTPUT"


@dataclass
class TaxonRecord:
    key: str  # "inat:48662", "gbif:2435099", "demo:1"
    source: str  # inaturalist | gbif | demo
    source_id: str
    scientific_name: str
    rank: str = ""
    common_name: Optional[str] = None
    classification: dict[str, str] = field(default_factory=dict)  # kingdom..genus
    observations_count: Optional[int] = None
    photo_url: Optional[str] = None
    photo_attribution: Optional[str] = None
    conservation_status: Optional[str] = None
    is_sensitive: bool = False
    url: Optional[str] = None
    provenance: str = LIVE
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OccurrenceRecord:
    source: str  # inaturalist | gbif | demo | user
    source_record_id: str
    scientific_name: str
    taxon_key: str
    lat: Optional[float]
    lon: Optional[float]
    uncertainty_m: Optional[float] = None
    event_date: Optional[str] = None
    year: Optional[int] = None
    basis_of_record: Optional[str] = None
    institution: Optional[str] = None
    dataset: Optional[str] = None
    recorded_by: Optional[str] = None
    country_code: Optional[str] = None
    derived_country_code: Optional[str] = None  # from offline reverse geocoding in QC
    url: Optional[str] = None
    photo_url: Optional[str] = None
    quality_grade: Optional[str] = None  # iNaturalist: research | needs_id | casual
    taxon_rank: Optional[str] = None
    taxon_ancestor_keys: list[str] = field(default_factory=list)
    captive_or_cultivated: Optional[bool] = None
    coordinates_obscured: bool = False
    issues: list[str] = field(default_factory=list)  # GBIF interpretation issues
    references: Optional[str] = None
    # Cross-source link (GBIF record that mirrors an iNaturalist observation)
    inat_observation_id: Optional[str] = None
    provenance: str = LIVE
    # Filled by the QC pipeline
    qc_status: str = "VALID"
    qc_reasons: list[str] = field(default_factory=list)
    duplicate_of: Optional[str] = None
    thinned: bool = False

    @property
    def source_prefix(self) -> str:
        return {"inaturalist": "inat"}.get(self.source, self.source)

    @property
    def uid(self) -> str:
        return f"{self.source}:{self.source_record_id}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["uid"] = self.uid
        return d
