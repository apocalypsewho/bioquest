"""ExplorationPriorityScore: transparent, explainable 0–100 index. No hidden ML.

score = Σ wᵢ·componentᵢ / Σ wᵢ over the components that are AVAILABLE (each 0–100).
Unavailable components (e.g. no species model in EXPLORE mode) are shown as "n/a" and excluded from the
denominator, so the weights are renormalised and the user sees exactly what was used.
"""
from __future__ import annotations

import numpy as np

DEFAULT_WEIGHTS = {
    "suitability": 0.30,
    "model_agreement": 0.10,
    "sampling_gap": 0.25,
    "biodiversity_potential": 0.15,
    "accessibility": 0.10,
    "taxonomic_uncertainty": 0.10,
}

# EXPLORE mode has no species model; accessibility matters more for a spontaneous outing.
EXPLORE_WEIGHTS = {
    "suitability": 0.0,
    "model_agreement": 0.0,
    "sampling_gap": 0.35,
    "biodiversity_potential": 0.30,
    "accessibility": 0.25,
    "taxonomic_uncertainty": 0.10,
}

DESCRIPTIONS = {
    "suitability": "Ensemble environmental suitability at the cell (×100). Not probability of occurrence.",
    "model_agreement": "Share of models (MaxEnt/RF/GLM) predicting the cell above their max-TSS threshold.",
    "sampling_gap": "Sampling Gap Score (low effort, few observers, far from records, few years).",
    "biodiversity_potential": "40% known richness within ~2 cells + 30% rare taxa (≤2 records in the area) "
                              "within ~2 cells + 30% terrain heterogeneity (elevation range) when an elevation "
                              "layer exists. Neighbourhood-based, so an unsampled cell is not penalised for "
                              "being unsampled.",
    "accessibility": "PROXY: straight-line distance from you and terrain slope. No road/trail network yet.",
    "taxonomic_uncertainty": "Share of nearby records not identified to species (where better IDs are needed).",
}


def accessibility(distance_km: float, slope_deg: float | None, max_km: float) -> float:
    d = max(0.0, 1 - distance_km / max_km)
    s = 1.0 if slope_deg is None or not np.isfinite(slope_deg) else max(0.0, 1 - slope_deg / 35)
    return 100 * (0.7 * d + 0.3 * s)


def accessibility_label(v: float) -> str:
    return "HIGH" if v >= 70 else ("MODERATE" if v >= 45 else "LOW")


def _norm(x: np.ndarray) -> np.ndarray:
    mx = np.nanmax(x) if np.isfinite(x).any() else 0
    return x / mx if mx > 0 else np.zeros_like(x)


def biodiversity_potential(g: dict, elev: np.ndarray | None, k: int = 2) -> tuple[np.ndarray, dict]:
    """0–100 per cell + the sub-components (each 0–100) for transparency."""
    H, W = g["n_records"].shape
    rare = {t for t, c in g["taxon_counts"].items() if c <= 2}
    rich = np.zeros((H, W))
    rar = np.zeros((H, W))
    het = np.full((H, W), np.nan)
    for a in range(H):
        for b in range(W):
            taxa = set()
            for aa in range(max(a - k, 0), min(a + k + 1, H)):
                for bb in range(max(b - k, 0), min(b + k + 1, W)):
                    taxa |= g["taxa_sets"][aa][bb]
            rich[a, b] = len(taxa)
            rar[a, b] = len(taxa & rare)
            if elev is not None:
                win = elev[max(a - 1, 0):a + 2, max(b - 1, 0):b + 2]
                if np.isfinite(win).any():
                    het[a, b] = np.nanmax(win) - np.nanmin(win)
    c_rich, c_rare = 100 * _norm(rich), 100 * _norm(rar)
    if np.isfinite(het).any():
        c_het = 100 * _norm(het)
        total = 0.4 * c_rich + 0.3 * c_rare + 0.3 * c_het
    else:
        c_het = het
        total = (0.4 * c_rich + 0.3 * c_rare) / 0.7
    return total, {"known_richness": c_rich, "rare_taxa": c_rare, "terrain_heterogeneity": c_het}


def score(components: dict[str, float | None], weights: dict[str, float] | None = None) -> dict:
    w = weights or DEFAULT_WEIGHTS
    used = {k: v for k, v in components.items() if v is not None and np.isfinite(v)}
    wsum = sum(w[k] for k in used)
    total = sum(w[k] * used[k] for k in used) / wsum if wsum else 0.0
    label = "VERY HIGH" if total >= 80 else "HIGH" if total >= 65 else "MEDIUM" if total >= 45 else "LOW"
    return {
        "score": round(total),
        "label": label,
        "components": [
            {"key": k, "value": None if components.get(k) is None else round(float(components[k])),
             "weight": w[k], "effective_weight": round(w[k] / wsum, 3) if k in used and wsum else 0,
             "used": k in used, "description": DESCRIPTIONS[k]}
            for k in w
        ],
        "formula": "score = Σ(weight × component) / Σ(weights of available components)",
    }
