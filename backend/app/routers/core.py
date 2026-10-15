"""Auth, sources/health, taxa, occurrences, sampling gap and EXPLORE."""
from __future__ import annotations

import asyncio
from typing import Literal

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import create_token, current_user, hash_password, verify_password
from ..config import get_settings
from ..db import get_db
from ..models import Occurrence, Taxon, User
from ..services import hub
from ..services.demo import DEMO_ORIGIN
from ..services.environment import PROVIDERS
from ..services.access import get_access
from ..services.explore import explore
from ..services.landcover import get_landcover
from ..services.literature import get_literature
from ..services.geo import Grid
from ..services.http import UpstreamError
from ..services.occurrence_qc import QCConfig, run_qc
from ..services.privacy import generalise_occurrence
from ..services.sampling import compute_gap
from ..services.types import DEMO, LIVE

router = APIRouter(prefix="/api")
Mode = Literal["live", "demo"]


# ------------------------------------------------------------------ auth
class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    display_name: str | None = None


def user_out(u: User) -> dict:
    return {"id": u.id, "username": u.username, "display_name": u.display_name or u.username, "role": u.role,
            "xp": u.xp, "default_coordinate_privacy": u.default_coordinate_privacy}


@router.post("/auth/register")
def register(c: Credentials, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.username == c.username)):
        raise HTTPException(409, "Username already taken")
    first = db.scalar(select(User).limit(1)) is None
    u = User(username=c.username, display_name=c.display_name or c.username, password_hash=hash_password(c.password),
             role="admin" if first else "user")
    db.add(u)
    db.commit()
    return {"token": create_token(u.id), "user": user_out(u)}


@router.post("/auth/login")
def login(c: Credentials, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.username == c.username))
    if not u or not verify_password(c.password, u.password_hash):
        raise HTTPException(401, "Invalid username or password")
    return {"token": create_token(u.id), "user": user_out(u)}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


class Prefs(BaseModel):
    display_name: str | None = None
    default_coordinate_privacy: Literal["public", "approximate", "private"] | None = None


@router.patch("/auth/me")
def update_me(p: Prefs, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if p.display_name:
        user.display_name = p.display_name
    if p.default_coordinate_privacy:
        user.default_coordinate_privacy = p.default_coordinate_privacy
    db.add(user)
    db.commit()
    return user_out(user)


# ------------------------------------------------------------------ health / sources
@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/sources")
def sources():
    s = get_settings()
    return {
        "inaturalist": {"api": s.inat_api_base, "oauth_configured": bool(s.inat_client_id and s.inat_client_secret),
                        "terms": "https://www.inaturalist.org/pages/terms",
                        "practices": "https://www.inaturalist.org/pages/api+recommended+practices"},
        "gbif": {"api": s.gbif_api_base, "terms": "https://www.gbif.org/terms",
                 "citation": "Cite each dataset (GBIF.org) — see record links."},
        "environment": {k: p.describe() for k, p in PROVIDERS.items()},
        "env_provider_default": s.env_provider,
        "land_cover": dict(zip(("available", "status"), get_landcover().available()),
                           label=get_landcover().label, directory=s.landcover_dir),
        "roads": {"api": s.overpass_url, "attribution": "© OpenStreetMap contributors (ODbL)"},
        "literature": {"apis": [f"{s.gbif_api_base}/literature/search", f"{s.crossref_api_base}/works"]},
    }


@router.get("/sources/ping")
async def ping():
    """Checks whether the live APIs are reachable from this server (useful behind restrictive networks)."""
    out = {}
    lit = get_literature()
    for name, coro in {"iNaturalist": hub.inat.search_taxa("Aves", 1),
                       "GBIF": hub.gbif.search_species("Aves", 1),
                       "Crossref": lit.crossref.get("works", rows=1, **{"query.bibliographic": "Aves"}),
                       "OpenStreetMap Overpass": get_access().client.request(
                           "POST", get_access().url, data={"data": "[out:json];node(1);out;"})}.items():
        try:
            await coro
            out[name] = {"reachable": True}
        except UpstreamError as e:
            out[name] = {"reachable": False, "detail": e.detail}
    return out


# ------------------------------------------------------------------ taxa
@router.get("/taxa/search")
async def taxa_search(q: str = Query(min_length=2), mode: Mode = "live"):
    return await hub.search_taxa(q, mode)


@router.get("/taxa/{key}")
async def taxon_profile(key: str, mode: Mode = "live", db: Session = Depends(get_db)):
    t, keys, errors = await hub.resolve_counterparts(key, mode)
    if not t:
        raise HTTPException(404 if not errors else 502, {"message": "Taxon not found", "errors": errors})
    stats: dict = {}
    if "demo" in keys:
        recs = hub.demo.occurrences(keys["demo"])
        dates = sorted(r.event_date for r in recs if r.event_date)
        stats = {"demo": {"records": len(recs), "last_observation": dates[-1] if dates else None,
                          "countries": [{"code": "PE", "count": len(recs)}]}}
        prov = DEMO
    else:
        prov = LIVE
        tasks = {}
        if "gbif" in keys:
            tasks["gbif"] = hub._safe(hub.gbif.facets(keys["gbif"].split(":")[1]), errors, "GBIF")
        if "inat" in keys:
            tid = keys["inat"].split(":")[1]
            tasks["inat_count"] = hub._safe(hub.inat.count(taxon_id=tid, geo="true"), errors, "iNaturalist")
            tasks["inat_last"] = hub._safe(hub.inat.api.get("observations", taxon_id=tid, per_page=1,
                                                            order_by="observed_on", order="desc"), errors,
                                           "iNaturalist")
        done = dict(zip(tasks, await asyncio.gather(*tasks.values())))
        if done.get("gbif"):
            f = done["gbif"]
            stats["gbif"] = {"records": f["total"], "countries": f["countries"],
                             "year_range": [f["years"][0], f["years"][-1]] if f["years"] else None}
        if done.get("inat_count") is not None:
            last = (done.get("inat_last") or {}).get("results") or [{}]
            stats["inaturalist"] = {"georeferenced_observations": done["inat_count"],
                                    "last_observation": last[0].get("observed_on")}
    # cache taxon
    if not db.scalar(select(Taxon).where(Taxon.source == t.source, Taxon.source_id == t.source_id)):
        db.add(Taxon(source=t.source, source_id=t.source_id, scientific_name=t.scientific_name, rank=t.rank,
                     common_name=t.common_name, classification=t.classification, is_sensitive=t.is_sensitive))
        db.commit()
    return {"taxon": t.to_dict(), "keys": keys, "stats": stats, "errors": errors, "provenance": prov}


def _persist(db: Session, records):
    existing = {
        (o.source, o.source_record_id): o
        for o in db.scalars(select(Occurrence).where(
            Occurrence.source_record_id.in_([r.source_record_id for r in records])))
    }
    for r in records:
        o = existing.get((r.source, r.source_record_id))
        if not o:
            o = Occurrence(source=r.source, source_record_id=r.source_record_id)
            db.add(o)
        o.taxon_key, o.scientific_name, o.lat, o.lon = r.taxon_key, r.scientific_name, r.lat, r.lon
        o.uncertainty_m, o.event_date, o.basis_of_record = r.uncertainty_m, r.event_date, r.basis_of_record
        o.institution, o.recorded_by, o.country_code, o.url = r.institution, r.recorded_by, r.country_code, r.url
        o.qc_status, o.qc_reasons, o.duplicate_of = r.qc_status, r.qc_reasons, r.duplicate_of
    db.commit()


async def qc_occurrences(key: str, mode: str, expected_countries: list[str]):
    data = await hub.occurrences(key, mode)
    t = data["taxon"]
    if not t:
        raise HTTPException(502 if data["errors"] else 404, {"message": "No data", "errors": data["errors"]})
    cfg = QCConfig(target_keys={k: v for k, v in data["keys"].items()}, target_rank=t.rank,
                   expected_countries=expected_countries)
    summary = run_qc(data["records"], cfg)
    return data, summary


@router.get("/taxa/{key}/occurrences")
async def taxon_occurrences(key: str, mode: Mode = "live", expected_countries: str = "",
                            db: Session = Depends(get_db)):
    countries = [c.strip() for c in expected_countries.split(",") if c.strip()]
    data, summary = await qc_occurrences(key, mode, countries)
    _persist(db, data["records"])
    t = data["taxon"]
    out = [generalise_occurrence(r.to_dict(), t.is_sensitive) for r in data["records"]]
    return {
        "taxon": t.to_dict(), "keys": data["keys"], "provenance": data.get("provenance"),
        "records": out, "qc": summary, "source_info": data.get("source_info", {}), "errors": data["errors"],
        "sensitive": t.is_sensitive,
        "sensitive_note": "Coordinates generalised to 0.2° because the taxon is sensitive." if t.is_sensitive else None,
    }


# ------------------------------------------------------------------ sampling gap + explore
@router.get("/gap")
async def gap_layer(minlon: float, minlat: float, maxlon: float, maxlat: float, mode: Mode = "live",
                    res: float = 0.02):
    if (maxlon - minlon) * (maxlat - minlat) / res ** 2 > 10_000:
        res = float(np.sqrt((maxlon - minlon) * (maxlat - minlat) / 10_000))
    grid = Grid([minlon, minlat, maxlon, maxlat], res)
    effort = await hub.effort_records(grid.bbox, mode)
    g = compute_gap(effort["records"], grid)
    return {"layer": grid.to_json(g["gap"]), "richness": grid.to_json(g["richness"]),
            "provenance": effort["provenance"], "note": effort["note"], "errors": effort["errors"],
            "weights": g["weights"],
            "stats": {"observations": int(g["n_records"].sum()), "taxa": len(g["taxon_counts"]),
                      "undersampled_cells": int((g["gap"] >= 60).sum()), "complete": effort["complete"]}}


class ExploreIn(BaseModel):
    mode: Mode = "live"
    lat: float
    lon: float
    radius_km: float = Field(20, ge=2, le=100)


@router.post("/explore")
async def do_explore(body: ExploreIn):
    return await explore(body.mode, body.lat, body.lon, body.radius_km)


@router.get("/demo/origin")
def demo_origin():
    return {**DEMO_ORIGIN, "provenance": DEMO}
