"""TaxonSuggestionProvider: interface for image-based taxonomic SUGGESTIONS (never confirmations).

No vision model ships with the MVP:
- NoVisionProvider (default): returns no suggestion and says so.
- DemoVisionProvider: returns a clearly labelled DEMO suggestion so the UI flow can be tried.
To plug a real model implement `suggest()` (e.g. a self-hosted classifier, or iNaturalist's computer-vision
endpoint ONLY if you obtain explicit access from iNaturalist — it is not a public API).

Language rules enforced here: outputs are "AI suggestion"; status is at most "needs_identification";
an unrecognised organism is NEVER reported as a new species.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

NEW_SPECIES_DISCLAIMER = (
    "An organism that an AI model does not recognise is NOT evidence of a new species. Establishing a new taxon "
    "requires taxonomic review by specialists: comparison with type material, the literature and diagnostic "
    "characters and, where appropriate, molecular evidence, followed by formal description in a peer-reviewed work."
)


class TaxonSuggestionProvider(ABC):
    code: str
    is_demo = False

    @abstractmethod
    def suggest(self, image: bytes | None, lat: float | None, lon: float | None, hint: str | None) -> dict: ...


class NoVisionProvider(TaxonSuggestionProvider):
    code = "none"

    def suggest(self, image, lat, lon, hint):
        return {"available": False, "label": "AI suggestion", "provider": self.code,
                "message": "No image-identification model is configured. Identify manually or via iNaturalist.",
                "suggestions": [], "disclaimer": NEW_SPECIES_DISCLAIMER}


class DemoVisionProvider(TaxonSuggestionProvider):
    code = "demo"
    is_demo = True

    def suggest(self, image, lat, lon, hint):
        return {
            "available": True, "label": "AI suggestion (DEMO)", "provider": self.code, "provenance": "DEMO DATA",
            "suggestions": [
                {"rank": "genus", "name": "Demoquestia", "confidence": 0.62},
                {"rank": "family", "name": "Demoquestiidae (DEMO)", "confidence": 0.81},
            ],
            "characters_to_check": ["chelicerae dentition", "flagellum shape (males)", "malleoli count",
                                    "propeltidium coloration"],
            "similar_taxa": ["Demoquestia andina", "Demoquestia nebulosa"],
            "status": "needs_identification",
            "disclaimer": NEW_SPECIES_DISCLAIMER,
        }


def get_vision(mode: str) -> TaxonSuggestionProvider:
    return DemoVisionProvider() if mode == "demo" else NoVisionProvider()


DISCOVERY_CATEGORIES = {
    "new_local_record": "🟢 New local record",
    "range_extension": "🔵 Range extension",
    "rare_observation": "🟣 Rare observation",
    "taxonomically_unresolved": "🟠 Taxonomically unresolved",
    "potentially_undescribed": "🔴 Potentially undescribed taxon",
}
EVIDENCE_LEVELS = {
    0: "Observation",
    1: "Verified observation",
    2: "Unusual occurrence",
    3: "Taxonomic interest",
    4: "Candidate taxon",
    5: "Requires formal taxonomic description",
}
RECORD_FLAGS = ["POTENTIAL TAXONOMICALLY INTERESTING RECORD", "UNUSUAL OBSERVATION", "POTENTIAL RANGE EXTENSION",
                "REQUIRES TAXONOMIC REVIEW"]
