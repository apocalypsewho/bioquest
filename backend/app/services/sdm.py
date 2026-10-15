"""DistributionModelService: species distribution models (MaxEnt, Random Forest, GLM) + ensemble.

Output semantics (important): every surface produced here is ENVIRONMENTAL SUITABILITY relative to the
study extent, estimated from presence-only data against random background / pseudo-absence points.
It is NOT a probability of occurrence and NOT confirmed presence.

Algorithms
- MaxEnt:   `elapid` (Python implementation of Maxent; Anderson 2023, JOSS 8(84):4930), cloglog output.
- RF:       scikit-learn RandomForestClassifier, balanced class weights (pseudo-absences = background).
- GLM:      binomial GLM (logistic regression) with linear + quadratic terms, balanced class weights.
- GAM:      pygam LogisticGAM with one penalised spline per predictor (Servén & Brummitt, pyGAM).
            Selectable instead of the GLM as the third model (algorithm id "gam").
Background
- "random": uniform random cells in the extent.
- "target_group": cells sampled in proportion to the density of records of a related group (same higher
  taxon / same observers' effort), so the background shares the sampling bias of the presences
  (Phillips et al. 2009, Ecol. Appl. 19:181–197).
Validation
- Spatial block cross-validation (k folds of spatial blocks) → AUC, TSS (threshold = max TSS on the
  training fold), confusion matrix. Also a random 70/30 split for reference.
"""
from __future__ import annotations

import time
import warnings as pywarnings
from dataclasses import dataclass, field

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler

from .environment import EnvironmentalDataProvider
from .geo import Grid
from .types import OccurrenceRecord

MIN_OCCURRENCES = 10
LOW_OCCURRENCES = 25
MAX_CELLS = 40_000
INSUFFICIENT_MSG = "Insufficient occurrence data for reliable model."

try:
    import elapid  # noqa: F401

    HAS_ELAPID = True
except Exception:  # pragma: no cover
    HAS_ELAPID = False

try:
    import pygam  # noqa: F401

    HAS_PYGAM = True
except Exception:  # pragma: no cover
    HAS_PYGAM = False


@dataclass
class SDMConfig:
    algorithms: tuple[str, ...] = ("maxent", "random_forest", "glm")
    include_questionable: bool = False
    n_background: int = 5000
    n_folds: int = 5
    collinearity_r: float = 0.7
    variables: list[str] | None = None
    bbox: list[float] | None = None
    res_deg: float | None = None
    seed: int = 42
    background: str = "random"  # "random" | "target_group"
    bias_points: list[tuple[float, float]] | None = None  # (lat, lon) of target-group records
    bias_source: str = ""


@dataclass
class SDMResult:
    status: str
    message: str = ""
    grid: Grid | None = None
    layers: dict[str, np.ndarray] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)
    n_raw: int = 0
    n_used: int = 0
    n_background: int = 0
    used_points: list[tuple[float, float]] = field(default_factory=list)


# ---------------------------------------------------------------------------- models

def _make(algo: str, n_pres: int, seed: int):
    if algo == "maxent":
        if not HAS_ELAPID:
            raise RuntimeError("MaxEnt unavailable: install 'elapid'")
        import elapid

        feats = ["linear", "quadratic", "hinge"] + (["product"] if n_pres >= 80 else [])
        return elapid.MaxentModel(feature_types=feats, beta_multiplier=1.5, transform="cloglog", n_cpus=1,
                                  random_state=seed)
    if algo == "random_forest":
        return RandomForestClassifier(n_estimators=300, min_samples_leaf=2, max_features="sqrt", oob_score=True,
                                      class_weight="balanced_subsample", n_jobs=-1, random_state=seed)
    if algo == "glm":
        return make_pipeline(StandardScaler(), PolynomialFeatures(degree=2, include_bias=False),
                             LogisticRegression(class_weight="balanced", C=1.0, max_iter=3000))
    if algo == "gam":
        if not HAS_PYGAM:
            raise RuntimeError("GAM unavailable: install 'pygam'")
        return _GAM()
    raise ValueError(f"unknown algorithm {algo}")


class _GAM:
    """Binomial GAM (pygam) with a penalised spline per (standardised) predictor; balanced weights."""

    def fit(self, X, y):
        from pygam import LogisticGAM, s as spline

        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        Z = (X - self.mu) / self.sd
        terms = spline(0, n_splines=8)
        for i in range(1, Z.shape[1]):
            terms = terms + spline(i, n_splines=8)
        w = np.where(y == 1, len(y) / (2 * max(y.sum(), 1)), len(y) / (2 * max((y == 0).sum(), 1)))
        from pygam.utils import OptimizationError

        # PIRLS can diverge under near-separation; increase the smoothing penalty until it converges.
        for lam in (1.0, 10.0, 100.0, 1000.0):
            try:
                self.m = LogisticGAM(terms, lam=lam, max_iter=200).fit(Z, y, weights=w)
                self.lam = lam
                return self
            except OptimizationError:
                continue
        raise RuntimeError("GAM did not converge even with strong smoothing (lam=1000)")

    def predict_proba(self, X):
        p = self.m.predict_proba((X - self.mu) / self.sd)
        return np.c_[1 - p, p]


def _predict(model, algo: str, X: np.ndarray) -> np.ndarray:
    if algo == "maxent":
        return np.asarray(model.predict(X), dtype=float)
    return model.predict_proba(X)[:, 1]


def _train_pred(model, algo: str, X: np.ndarray) -> np.ndarray:
    """Training-set predictions for threshold selection; out-of-bag for RF (in-bag RF scores are ~1)."""
    if algo == "random_forest" and hasattr(model, "oob_decision_function_"):
        p = model.oob_decision_function_[:, 1]
        return np.nan_to_num(p, nan=0.0)
    return _predict(model, algo, X)


def _fit(algo, X, y, seed):
    m = _make(algo, int(y.sum()), seed)
    with pywarnings.catch_warnings():
        pywarnings.simplefilter("ignore")
        m.fit(X, y)
    return m


def _best_tss_threshold(y, p) -> tuple[float, float]:
    best_t, best = 0.5, -1.0
    for t in np.unique(np.quantile(p, np.linspace(0.01, 0.99, 99))):
        pred = p >= t
        sens = (pred & (y == 1)).sum() / max((y == 1).sum(), 1)
        spec = (~pred & (y == 0)).sum() / max((y == 0).sum(), 1)
        if sens + spec - 1 > best:
            best, best_t = sens + spec - 1, float(t)
    return best_t, best


def _evaluate(y, p, t):
    pred = (p >= t).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    sens = tp / max(tp + fn, 1)
    spec = tn / max(tn + fp, 1)
    auc = roc_auc_score(y, p) if len(np.unique(y)) == 2 else float("nan")
    return {"auc": float(auc), "tss": float(sens + spec - 1), "sensitivity": float(sens), "specificity": float(spec),
            "confusion_matrix": {"tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn)}}


def _spatial_folds(lat, lon, block_deg, k, rng):
    blocks = np.floor(lat / block_deg).astype(int) * 100_000 + np.floor(lon / block_deg).astype(int)
    ub = np.unique(blocks)
    rng.shuffle(ub)
    fold_of = {b: i % k for i, b in enumerate(ub)}
    return np.array([fold_of[b] for b in blocks])


# ---------------------------------------------------------------------------- service

class DistributionModelService:
    """Frontend → API → DistributionModelService → (sklearn/elapid) → gridded suitability → map."""

    def choose_grid(self, records: list[OccurrenceRecord], provider: EnvironmentalDataProvider,
                    cfg: SDMConfig) -> Grid:
        if cfg.bbox:
            bbox = cfg.bbox
        else:
            lats = np.array([r.lat for r in records])
            lons = np.array([r.lon for r in records])
            span = max(lats.max() - lats.min(), lons.max() - lons.min(), 0.5)
            buf = max(0.5, 0.25 * span)
            bbox = [max(lons.min() - buf, -180), max(lats.min() - buf, -90),
                    min(lons.max() + buf, 180), min(lats.max() + buf, 90)]
        res = cfg.res_deg or provider.native_res_deg
        area_cells = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) / res ** 2
        if area_cells > MAX_CELLS:
            res = float(np.sqrt((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) / MAX_CELLS))
            # snap to a multiple of the native resolution
            res = float(np.ceil(res / provider.native_res_deg) * provider.native_res_deg)
        return Grid(bbox, res)

    def run(self, records: list[OccurrenceRecord], provider: EnvironmentalDataProvider,
            cfg: SDMConfig | None = None) -> SDMResult:
        cfg = cfg or SDMConfig()
        t0 = time.time()
        rng = np.random.default_rng(cfg.seed)
        ok_status = {"VALID", "QUESTIONABLE"} if cfg.include_questionable else {"VALID"}
        usable = [r for r in records if r.qc_status in ok_status and r.lat is not None]
        res = SDMResult(status="running", n_raw=len(records))
        res.warnings.append(
            "Output is relative ENVIRONMENTAL SUITABILITY within the study extent, not probability of occurrence "
            "or confirmed presence.")
        if provider.is_demo:
            res.warnings.append("Environmental predictors are SYNTHETIC (DEMO). Do not interpret ecologically.")
        if len(usable) < MIN_OCCURRENCES:
            res.status, res.message, res.n_used = "insufficient_data", INSUFFICIENT_MSG, len(usable)
            res.warnings.append(f"Only {len(usable)} usable records after QC (minimum {MIN_OCCURRENCES}). "
                                "No map was generated to avoid a misleading prediction.")
            return res

        grid = self.choose_grid(usable, provider, cfg)
        res.grid = grid
        env = provider.grid(grid, cfg.variables)
        names = [k for k, v in env.items() if np.isfinite(v).any()]
        stack = np.stack([env[k] for k in names], axis=-1)  # (H, W, V)
        valid_cell = np.isfinite(stack).all(axis=-1)

        # presences → unique cells (thinning to the model resolution = 1 record per cell)
        row, col, inside = grid.index([r.lat for r in usable], [r.lon for r in usable])
        cells = {(int(a), int(b)) for a, b, i in zip(row, col, inside) if i and valid_cell[a, b]}
        n_outside = int((~inside).sum())
        if n_outside:
            res.warnings.append(f"{n_outside} records fall outside the study extent and were not used.")
        dropped_nodata = sum(1 for a, b, i in zip(row, col, inside) if i and not valid_cell[a, b])
        if dropped_nodata:
            res.warnings.append(f"{dropped_nodata} records fall on cells without environmental data (sea/no-data).")
        pres_cells = np.array(sorted(cells))
        res.n_used = len(pres_cells)
        if res.n_used < MIN_OCCURRENCES:
            res.status, res.message = "insufficient_data", INSUFFICIENT_MSG
            res.warnings.append(f"Only {res.n_used} unique occupied cells at {grid.res:.3f}° after spatial thinning.")
            return res
        if res.n_used < LOW_OCCURRENCES:
            res.warnings.append(f"Low sample size ({res.n_used} occupied cells): predictions are highly uncertain.")
        thinned = len(usable) - res.n_used
        if thinned > 0:
            res.warnings.append(f"Spatial thinning kept 1 record per {grid.res:.3f}° cell ({thinned} records "
                                "collapsed) to reduce sampling bias and spatial autocorrelation.")
        LON, LAT = grid.centers()
        res.used_points = [(float(LAT[a, b]), float(LON[a, b])) for a, b in pres_cells]

        # background / pseudo-absences: random cells in the extent (not occupied)
        cand = np.argwhere(valid_cell)
        occ = {(a, b) for a, b in pres_cells}
        cand = np.array([c for c in cand if (c[0], c[1]) not in occ])
        nb = min(cfg.n_background, len(cand))
        weights_bg = None
        if cfg.background == "target_group" and cfg.bias_points:
            br, bc, bin_ = grid.index([p[0] for p in cfg.bias_points], [p[1] for p in cfg.bias_points])
            dens = np.zeros(valid_cell.shape)
            np.add.at(dens, (br[bin_], bc[bin_]), 1.0)
            w = dens[cand[:, 0], cand[:, 1]]
            n_bias_cells = int((w > 0).sum())
            if n_bias_cells >= 20:
                weights_bg = w / w.sum()
                nb = min(nb, n_bias_cells)
            else:
                res.warnings.append(f"Target-group background requested but only {n_bias_cells} cells have "
                                    "target-group records; fell back to random background.")
        bg = cand[rng.choice(len(cand), nb, replace=False, p=weights_bg)]
        res.n_background = nb
        if weights_bg is not None:
            res.metrics["background"] = {"method": "target_group", "source": cfg.bias_source,
                                         "n_bias_records": len(cfg.bias_points or [])}
            res.warnings.append(
                f"Pseudo-absences: {nb} TARGET-GROUP background cells, sampled in proportion to records of "
                f"{cfg.bias_source or 'a related group'} (bias correction, Phillips et al. 2009). This assumes the "
                "target group was sampled with the same bias as the species.")
        else:
            res.metrics["background"] = {"method": "random"}
            res.warnings.append(
                f"Pseudo-absences: {nb} random background cells from the extent. Background is NOT bias-corrected "
                "(sampling bias in the presences is partly reflected in the model).")

        # collinearity (Pearson on background)
        Xb = stack[bg[:, 0], bg[:, 1]]
        corr = np.corrcoef(Xb, rowvar=False)
        keep: list[int] = []
        dropped = []
        for i in range(len(names)):
            clash = [j for j in keep if abs(corr[i, j]) > cfg.collinearity_r]
            if clash:
                dropped.append(f"{names[i]} (|r|={abs(corr[i, clash[0]]):.2f} with {names[clash[0]]})")
            else:
                keep.append(i)
        if dropped:
            res.warnings.append(f"Collinearity: dropped {', '.join(dropped)} (threshold |r|>{cfg.collinearity_r}).")
        names_k = [names[i] for i in keep]
        res.variables = names_k
        res.metrics["correlation_matrix"] = {"variables": names, "r": np.round(corr, 3).tolist()}

        Xp = stack[pres_cells[:, 0], pres_cells[:, 1]][:, keep]
        Xb = Xb[:, keep]
        X = np.vstack([Xp, Xb])
        y = np.r_[np.ones(len(Xp)), np.zeros(len(Xb))]
        lat_all = np.r_[LAT[pres_cells[:, 0], pres_cells[:, 1]], LAT[bg[:, 0], bg[:, 1]]]
        lon_all = np.r_[LON[pres_cells[:, 0], pres_cells[:, 1]], LON[bg[:, 0], bg[:, 1]]]

        # spatial block CV
        ext = max(grid.maxlat - grid.minlat, grid.maxlon - grid.minlon)
        block = max(ext / 6, grid.res * 5)
        folds = _spatial_folds(lat_all, lon_all, block, cfg.n_folds, rng)
        Xall_cells = stack[valid_cell][:, keep]

        algos = [a for a in cfg.algorithms if (a != "maxent" or HAS_ELAPID) and (a != "gam" or HAS_PYGAM)]
        if "maxent" in cfg.algorithms and not HAS_ELAPID:
            res.warnings.append("MaxEnt skipped: 'elapid' is not installed on the model service.")
        if "gam" in cfg.algorithms and not HAS_PYGAM:
            res.warnings.append("GAM skipped: 'pygam' is not installed on the model service.")
        for algo in algos:
            fold_metrics = []
            for k in range(cfg.n_folds):
                tr, te = folds != k, folds == k
                if y[te].sum() == 0 or y[tr].sum() < 5 or (y[te] == 0).sum() == 0:
                    continue
                m = _fit(algo, X[tr], y[tr], cfg.seed)
                t, _ = _best_tss_threshold(y[tr], _train_pred(m, algo, X[tr]))
                fold_metrics.append(_evaluate(y[te], _predict(m, algo, X[te]), t))
            Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, stratify=y, random_state=cfg.seed)
            m = _fit(algo, Xtr, ytr, cfg.seed)
            t, _ = _best_tss_threshold(ytr, _train_pred(m, algo, Xtr))
            random_split = _evaluate(yte, _predict(m, algo, Xte), t)

            final = _fit(algo, X, y, cfg.seed)
            p_train = _train_pred(final, algo, X)
            thr, _ = _best_tss_threshold(y, p_train)
            pred = np.full(valid_cell.shape, np.nan)
            pred[valid_cell] = _predict(final, algo, Xall_cells)
            res.layers[algo] = pred
            res.thresholds[algo] = thr

            def agg(key):
                vals = [f[key] for f in fold_metrics if np.isfinite(f[key])]
                return {"mean": float(np.mean(vals)), "sd": float(np.std(vals)), "n_folds": len(vals)} if vals else None

            cm = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
            for f in fold_metrics:
                for kk in cm:
                    cm[kk] += f["confusion_matrix"][kk]
            imp = None
            if algo == "random_forest":
                imp = {n: round(float(v), 4) for n, v in zip(names_k, final.feature_importances_)}
            res.metrics[algo] = {
                "spatial_cv": {"auc": agg("auc"), "tss": agg("tss"), "confusion_matrix_pooled": cm,
                               "block_size_deg": round(block, 3)},
                "random_split_70_30": random_split,
                "threshold_max_tss": round(thr, 4),
                "variable_importance": imp,
            }

        # ensemble: min-max rescale each model, weight by (spatial AUC - 0.5) for models with AUC >= 0.7
        scaled, weights = {}, {}
        for algo, layer in res.layers.items():
            lo, hi = np.nanmin(layer), np.nanmax(layer)
            scaled[algo] = (layer - lo) / (hi - lo) if hi > lo else layer * 0
            auc = (res.metrics[algo]["spatial_cv"]["auc"] or {}).get("mean", float("nan"))
            weights[algo] = max(auc - 0.5, 0) if np.isfinite(auc) and auc >= 0.7 else 0.0
        if sum(weights.values()) == 0:
            weights = {a: 1.0 for a in scaled}
            res.warnings.append("No model reached spatial-CV AUC ≥ 0.7: ensemble is an unweighted mean and should "
                                "be treated as unreliable.")
        wsum = sum(weights.values())
        ens = sum(scaled[a] * w for a, w in weights.items()) / wsum
        res.layers["ensemble"] = ens
        agree = sum((res.layers[a] >= res.thresholds[a]).astype(float) for a in scaled)
        agree[~valid_cell] = np.nan
        res.layers["agreement"] = agree
        ens_pres = ens[pres_cells[:, 0], pres_cells[:, 1]]
        res.thresholds["ensemble"] = float(np.nanpercentile(ens_pres, 10))  # 10th-percentile training presence
        res.metrics["ensemble"] = {
            "method": "weighted mean of min-max rescaled model outputs; weight = spatial-CV AUC − 0.5 (AUC ≥ 0.7)",
            "weights": {a: round(w / wsum, 3) for a, w in weights.items()},
            "threshold_p10": round(res.thresholds["ensemble"], 4),
            "n_models": len(scaled),
        }

        # extrapolation (cells outside the training range of any predictor)
        lo, hi = X.min(0), X.max(0)
        outside = ((Xall_cells < lo) | (Xall_cells > hi)).any(1)
        frac = float(outside.mean()) if len(outside) else 0.0
        extr = np.full(valid_cell.shape, np.nan)
        extr[valid_cell] = outside.astype(float)
        res.layers["extrapolation"] = extr
        res.metrics["extrapolation_fraction"] = round(frac, 4)
        if frac > 0.05:
            res.warnings.append(f"Extrapolation: {frac:.0%} of the extent lies outside the environmental range of "
                                "the training data; predictions there are unreliable.")
        res.warnings.append("Spatial autocorrelation: presences are clustered; validation uses spatial blocks "
                            f"(~{block:.2f}°) but metrics may still be optimistic.")
        res.warnings.append("AUC/TSS are computed against background points (presence-background), not true "
                            "absences; they measure discrimination from the background, not accuracy.")
        res.metrics["runtime_s"] = round(time.time() - t0, 2)
        res.status = "completed"
        return res
