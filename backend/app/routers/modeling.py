"""Distribution modelling endpoints. Runs are executed off the event loop (in-process job runner).

The job runner is deliberately simple (asyncio task + thread). For production swap `_launch` for a
Celery/RQ task — the ModelRun row already carries status, so the API contract does not change.
"""
from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import optional_user
from ..db import SessionLocal, get_db
from ..models import ModelRun, Prediction, User
from ..services.environment import NotConfigured, get_provider
from ..services.explore import species_zone
from ..services.geo import Grid
from ..services.hub import target_group_points
from ..services.sdm import DistributionModelService, SDMConfig
from ..services.types import MODEL
from .core import qc_occurrences

router = APIRouter(prefix="/api/models")
svc = DistributionModelService()
_tasks: set = set()


class ModelIn(BaseModel):
    taxon_key: str
    mode: Literal["live", "demo"] = "live"
    include_questionable: bool = False
    expected_countries: list[str] = []
    env_provider: str | None = None
    model3: Literal["glm", "gam"] = "glm"
    background: Literal["random", "target_group"] = "random"


def _provider_for(mode: str, requested: str | None):
    if mode == "demo":
        return get_provider("demo")
    p = get_provider(requested or "worldclim")
    if p.is_demo:
        raise HTTPException(400, "DEMO environmental layers cannot be combined with LIVE occurrence data.")
    ok, msg = p.available()
    if not ok:
        raise HTTPException(409, {"message": "No real environmental layers available for LIVE modelling.",
                                  "detail": msg,
                                  "fix": "Run: python scripts/download_worldclim.py --res 10m  (WorldClim v2.1)"})
    return p


async def _execute(run_id: int, body: ModelIn):
    db = SessionLocal()
    run = db.get(ModelRun, run_id)
    try:
        data, summary = await qc_occurrences(body.taxon_key, body.mode, body.expected_countries)
        run.qc_summary = summary
        run.scientific_name = data["taxon"].scientific_name
        run.n_occurrences_raw = len(data["records"])
        provider = _provider_for(body.mode, body.env_provider)
        cfg = SDMConfig(include_questionable=body.include_questionable,
                        algorithms=("maxent", "random_forest", body.model3), background=body.background)
        if body.background == "target_group":
            usable = [r for r in data["records"] if r.lat is not None and
                      r.qc_status in ({"VALID", "QUESTIONABLE"} if body.include_questionable else {"VALID"})]
            if usable:
                bbox = svc.choose_grid(usable, provider, cfg).bbox
                tg = await target_group_points(body.taxon_key, body.mode, bbox)
                cfg.bias_points, cfg.bias_source = tg["points"], tg["source"]
                tg_errors = [f"Target-group background: {e['service']}: {e['detail']}" for e in tg["errors"]]
            else:
                tg_errors = []
        else:
            tg_errors = []
        res = await asyncio.to_thread(svc.run, data["records"], provider, cfg)
        run.status = res.status
        run.warnings = res.warnings + tg_errors + ([res.message] if res.message else [])
        run.metrics = {"mode": body.mode, **res.metrics, "used_points": res.used_points[:2000]}
        run.variables = res.variables
        run.n_occurrences_used = res.n_used
        run.n_background = res.n_background
        if res.grid:
            run.resolution_deg = res.grid.res
            run.bbox = res.grid.bbox
            for algo, layer in res.layers.items():
                db.add(Prediction(model_run_id=run.id, algorithm=algo, grid=res.grid.to_json(layer),
                                  threshold=res.thresholds.get(algo)))
    except HTTPException as e:
        run.status = "failed"
        run.warnings = [str(e.detail)]
    except Exception as e:  # surfaced to the UI, never hidden
        run.status = "failed"
        run.warnings = [f"{e.__class__.__name__}: {e}"]
    db.add(run)
    db.commit()
    db.close()


@router.post("")
async def create_run(body: ModelIn, db: Session = Depends(get_db), user: User | None = Depends(optional_user)):
    provider = _provider_for(body.mode, body.env_provider)  # fail fast if no env layers
    run = ModelRun(user_id=user.id if user else None, taxon_key=body.taxon_key, scientific_name="", status="running",
                   provenance=MODEL + (" · DEMO input" if body.mode == "demo" else " · LIVE input"),
                   env_provider=provider.code, resolution_deg=0, metrics={"mode": body.mode})
    db.add(run)
    db.commit()
    t = asyncio.create_task(_execute(run.id, body))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    return {"id": run.id, "status": run.status}


def run_out(run: ModelRun, db: Session) -> dict:
    preds = db.scalars(select(Prediction).where(Prediction.model_run_id == run.id)).all()
    metrics = dict(run.metrics or {})
    return {
        "id": run.id, "taxon_key": run.taxon_key, "scientific_name": run.scientific_name, "status": run.status,
        "provenance": run.provenance, "env_provider": run.env_provider,
        "env_provider_label": get_provider(run.env_provider).label if run.env_provider else None,
        "variables": run.variables, "resolution_deg": run.resolution_deg, "bbox": run.bbox,
        "n_occurrences_raw": run.n_occurrences_raw, "n_occurrences_used": run.n_occurrences_used,
        "n_background": run.n_background, "metrics": metrics, "warnings": run.warnings, "qc": run.qc_summary,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "layers": sorted(p.algorithm for p in preds),
        "output_type": "environmental suitability (relative, 0–1) — not probability of occurrence",
    }


@router.get("")
def list_runs(db: Session = Depends(get_db)):
    runs = db.scalars(select(ModelRun).order_by(ModelRun.id.desc()).limit(50)).all()
    return [{"id": r.id, "taxon_key": r.taxon_key, "scientific_name": r.scientific_name, "status": r.status,
             "provenance": r.provenance, "n_used": r.n_occurrences_used, "created_at": r.created_at.isoformat()}
            for r in runs]


@router.get("/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(ModelRun, run_id)
    if not run:
        raise HTTPException(404)
    return run_out(run, db)


@router.get("/{run_id}/layers/{algo}")
def get_layer(run_id: int, algo: str, db: Session = Depends(get_db)):
    p = db.scalar(select(Prediction).where(Prediction.model_run_id == run_id, Prediction.algorithm == algo))
    if not p:
        raise HTTPException(404)
    return {"algorithm": algo, "grid": p.grid, "threshold": p.threshold, "provenance": db.get(ModelRun, run_id).provenance}


@router.get("/{run_id}/cell")
def cell(run_id: int, lat: float, lon: float, db: Session = Depends(get_db)):
    run = db.get(ModelRun, run_id)
    preds = {p.algorithm: p for p in db.scalars(select(Prediction).where(Prediction.model_run_id == run_id))}
    if not run or "ensemble" not in preds:
        raise HTTPException(404)
    g0 = preds["ensemble"].grid
    grid = Grid.from_shape(g0["bbox"][0], g0["bbox"][3], g0["res"], g0["width"], g0["height"])
    row, col, inside = grid.index([lat], [lon])
    if not inside[0]:
        return {"inside": False}
    i = int(row[0]) * grid.width + int(col[0])
    vals = {a: p.grid["values"][i] for a, p in preds.items()}
    n_models = run.metrics.get("ensemble", {}).get("n_models", 3)
    return {
        "inside": True, "values": vals, "thresholds": {a: p.threshold for a, p in preds.items()},
        "environmental_suitability": vals.get("ensemble"),
        "model_agreement": None if vals.get("agreement") is None else f"{int(vals['agreement'])}/{n_models}",
        "extrapolation": bool(vals.get("extrapolation")),
        "provenance": run.provenance,
    }


class ZoneIn(BaseModel):
    lat: float | None = None
    lon: float | None = None
    max_km: float = 120


@router.post("/{run_id}/zone")
async def zone(run_id: int, body: ZoneIn, db: Session = Depends(get_db)):
    run = db.get(ModelRun, run_id)
    if not run or run.status != "completed":
        raise HTTPException(409, "Model run is not completed")
    preds = {p.algorithm: p.grid for p in db.scalars(select(Prediction).where(Prediction.model_run_id == run_id))}
    mode = run.metrics.get("mode", "live")
    known = [tuple(p) for p in run.metrics.get("used_points", [])]
    return await species_zone(mode, run, preds, known, body.lat, body.lon, body.max_km)
