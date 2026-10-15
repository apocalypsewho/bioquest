"""Field-sampling guidance attached to missions, by taxon group and habitat.

GENERAL GUIDANCE drawn from standard field-methods practice (e.g. timed searches, point counts, visual
encounter surveys); it is not a site-specific protocol and does not replace permits or local regulations.
"""
from __future__ import annotations

GROUPS = {
    "Aves": ["Point counts of 10 min at ≥200 m spacing, first 3–4 h after dawn.",
             "Record calls (audio) for species heard but not seen.",
             "Note behaviour (breeding, feeding) — it raises the value of the record."],
    "Amphibia": ["Visual encounter survey along streams/ponds after dusk; 1–2 h per transect.",
                 "Record advertisement calls; note air/water temperature and humidity.",
                 "Avoid handling; if needed, use wet nitrile gloves and disinfect boots between sites (chytrid)."],
    "Reptilia": ["Timed searches in sunny microhabitats (rocks, logs, edges) mid-morning.",
                 "Photograph dorsal, lateral and ventral views when possible; do not capture without permits."],
    "Insecta": ["Time-constrained search (e.g. 30 min) per microhabitat; photograph wing venation and genitalia "
                "region when relevant for ID.",
                "Light trapping at night only with permits; record trap type and hours."],
    "Arachnida": ["Night search with a headlamp (eye-shine for spiders); beat vegetation onto a sheet.",
                  "Photograph eye arrangement and the dorsal pattern."],
    "Mollusca": ["Search leaf litter and under logs after rain; photograph the shell aperture and the animal."],
    "Mammalia": ["Look for indirect evidence (tracks, scat, burrows); camera traps for 2+ weeks if available.",
                 "Never approach or bait wild mammals."],
    "Plantae": ["Plot-based survey (e.g. 10×10 m); photograph habit, leaves (both sides), flowers and fruits.",
                "Record phenology and substrate; collect specimens only with permits."],
    "Fungi": ["Photograph cap, gills/pores, stipe base and substrate; note smell and spore print colour.",
              "Search after rain; record host plant or wood type."],
}
HABITATS = {
    "forest": "Survey edge and interior separately; check epiphytes, bark and leaf litter.",
    "tree": "Survey edge and interior separately; check epiphytes, bark and leaf litter.",
    "grass": "Walk parallel transects 20–50 m apart; check under stones and at tussock bases.",
    "shrub": "Search shrub bases and flowering shrubs; beat foliage for invertebrates.",
    "wetland": "Search margins and emergent vegetation; mind unstable ground.",
    "water": "Search banks and margins; record water temperature.",
    "bare": "Search under rocks and in crevices; cover the area systematically.",
    "crop": "Focus on margins, hedgerows and remnant vegetation; ask landowner permission.",
    "built": "Search green spaces and walls; ask for permission on private property.",
}
ALWAYS = ["Record GPS accuracy, time spent and number of observers (sampling effort) — absences only matter "
          "with effort.",
          "Photograph every organism you cannot identify; several angles plus a scale reference.",
          "Respect protected areas, private land and permits; do not collect without authorization."]


def recommendations(group: str | None, habitat: str | None) -> dict:
    g = group if group in GROUPS else None
    tips = list(GROUPS[g]) if g else ["All-taxa rapid survey: 30-min timed searches in each distinct microhabitat."]
    h = (habitat or "").lower()
    hab_tip = next((v for k, v in HABITATS.items() if k in h), None)
    return {"group": g or "all taxa", "habitat": habitat or "unknown", "taxon_methods": tips,
            "habitat_tip": hab_tip, "always": ALWAYS,
            "label": "GUIDANCE — general field-methods practice, not a site-specific protocol."}
