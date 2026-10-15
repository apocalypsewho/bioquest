"""Missions, expeditions, observations (incl. offline sync), discoveries, profile, iNaturalist OAuth."""
from __future__ import annotations

import datetime as dt
import math
import os
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import create_token, current_user, decode_token
from ..config import get_settings
from ..db import get_db
from ..models import (
    Discovery,
    Expedition,
    ExternalAccount,
    Mission,
    ModelRun,
    Observation,
    Photo,
    Prediction,
    Project,
    ProjectObservation,
    User,
    XPEvent,
)
from ..services import hub
from ..services.anomaly import assess
from ..services.environment import NotConfigured, get_provider
from ..services.geo import Grid, haversine_km
from ..services.literature import get_literature
from ..services.sampling_guide import recommendations
from ..services.http import UpstreamError
from ..services.privacy import public_coords
from ..services.storage import get_storage
from ..services.taxonomy_ai import (
    DISCOVERY_CATEGORIES,
    EVIDENCE_LEVELS,
    NEW_SPECIES_DISCLAIMER,
    RECORD_FLAGS,
    get_vision,
)
from ..services.xp import XP_RULES, award

router = APIRouter(prefix="/api")


# ------------------------------------------------------------------ missions
class MissionIn(BaseModel):
    zone: dict
    user_lat: float | None = None
    user_lon: float | None = None


def _taxon_group(z: dict) -> str | None:
    t = z.get("target") or {}
    cls = (t.get("classification") or {})
    return t.get("group") or cls.get("class") or ({"Plantae": "Plantae", "Fungi": "Fungi"}.get(cls.get("kingdom")))


def mission_out(m: Mission) -> dict:
    z = m.zone or {}
    hab = (z.get("habitat") or {}).get("habitat")
    return {"guidance": recommendations(_taxon_group(z), hab),"id": m.id, "code": m.code, "target_taxon_key": m.target_taxon_key, "target_name": m.target_name,
            "objective": m.objective, "center": {"lat": m.center_lat, "lon": m.center_lon}, "radius_m": m.radius_m,
            "area_km2": m.area_km2, "distance_km": m.distance_km, "priority": m.priority, "zone": m.zone,
            "status": m.status, "provenance": m.provenance, "model_run_id": m.model_run_id,
            "created_at": m.created_at.isoformat()}


@router.post("/missions")
async def create_mission(body: MissionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    z = body.zone
    target = z.get("target") or {}
    if target.get("key") and not target.get("classification"):
        mode = "demo" if target["key"].startswith("demo:") else "live"
        try:
            t, _, _ = await hub.resolve_counterparts(target["key"], mode)
            if t:
                target["classification"] = t.classification
                target["group"] = t.extra.get("iconic_taxon_name")
        except Exception:  # guidance falls back to all-taxa methods
            pass
    n = (db.scalar(select(func.max(Mission.id))) or 0) + 1
    m = Mission(
        user_id=user.id, code=f"{240 + n:06d}", target_taxon_key=target.get("key"),
        target_name=target.get("scientific_name"),
        objective=z.get("objective") or "Survey an under-sampled area and document all organisms found.",
        center_lat=z["center"]["lat"], center_lon=z["center"]["lon"], radius_m=z["radius_m"], area_km2=z["area_km2"],
        distance_km=z.get("distance_km"), priority=z.get("priority"), zone=z, model_run_id=z.get("model_run_id"),
        provenance=z.get("provenance", "LIVE DATA"),
    )
    db.add(m)
    db.flush()
    award(db, user, "explore", f"mission:{m.id}")
    db.commit()
    return mission_out(m)


@router.get("/missions")
def list_missions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [mission_out(m) for m in db.scalars(select(Mission).where(Mission.user_id == user.id)
                                                .order_by(Mission.id.desc()))]


@router.get("/missions/{mid}")
def get_mission(mid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = db.get(Mission, mid)
    if not m or m.user_id != user.id:
        raise HTTPException(404)
    return mission_out(m)


@router.patch("/missions/{mid}")
def set_mission_status(mid: int, status: Literal["active", "completed", "abandoned"],
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = db.get(Mission, mid)
    if not m or m.user_id != user.id:
        raise HTTPException(404)
    m.status = status
    db.commit()
    return mission_out(m)


# ------------------------------------------------------------------ expeditions
class ExpeditionIn(BaseModel):
    mission_id: int | None = None
    name: str = ""
    is_demo: bool = False


def _route_km(route) -> float:
    d = 0.0
    for a, b in zip(route, route[1:]):
        d += float(haversine_km(a[1], a[0], b[1], b[0]))
    return d


def expedition_out(e: Expedition, db: Session) -> dict:
    obs = db.scalars(select(Observation).where(Observation.expedition_id == e.id)).all()
    taxa = {o.taxon_name for o in obs if o.taxon_name}
    unusual = db.scalar(select(func.count(Discovery.id)).where(Discovery.observation_id.in_([o.id for o in obs]))) or 0
    habitats = {o.habitat for o in obs if o.habitat}
    end = e.ended_at or dt.datetime.now(dt.timezone.utc)
    start = e.started_at if e.started_at.tzinfo else e.started_at.replace(tzinfo=dt.timezone.utc)
    end = end if end.tzinfo else end.replace(tzinfo=dt.timezone.utc)
    return {"id": e.id, "name": e.name, "mission_id": e.mission_id, "started_at": e.started_at.isoformat(),
            "ended_at": e.ended_at.isoformat() if e.ended_at else None, "route": e.route,
            "distance_km": round(e.distance_km, 2), "duration_min": round((end - start).total_seconds() / 60),
            "observations": len(obs), "taxa": len(taxa), "habitats": len(habitats), "unusual_records": unusual,
            "photos": sum(len(o.photos) for o in obs), "is_demo": e.is_demo, "status": "complete" if e.ended_at else "active"}


@router.post("/expeditions")
def start_expedition(body: ExpeditionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = Expedition(user_id=user.id, mission_id=body.mission_id, name=body.name or "Expedition", is_demo=body.is_demo)
    db.add(e)
    db.commit()
    return expedition_out(e, db)


class TrackIn(BaseModel):
    points: list[list[float | str]]  # [lon, lat, iso_time]


@router.post("/expeditions/{eid}/track")
def add_track(eid: int, body: TrackIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = db.get(Expedition, eid)
    if not e or e.user_id != user.id:
        raise HTTPException(404)
    e.route = list(e.route or []) + body.points
    e.distance_km = _route_km(e.route)
    db.commit()
    return {"points": len(e.route), "distance_km": round(e.distance_km, 2)}


@router.post("/expeditions/{eid}/finish")
def finish_expedition(eid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = db.get(Expedition, eid)
    if not e or e.user_id != user.id:
        raise HTTPException(404)
    e.ended_at = dt.datetime.now(dt.timezone.utc)
    if e.mission_id:
        m = db.get(Mission, e.mission_id)
        if m:
            m.status = "completed"
    db.commit()
    return expedition_out(e, db)


@router.get("/expeditions")
def list_expeditions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [expedition_out(e, db) for e in db.scalars(select(Expedition).where(Expedition.user_id == user.id)
                                                      .order_by(Expedition.id.desc()))]


@router.get("/expeditions/{eid}")
def get_expedition(eid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = db.get(Expedition, eid)
    if not e or e.user_id != user.id:
        raise HTTPException(404)
    out = expedition_out(e, db)
    out["observation_list"] = [obs_out(o, user) for o in
                               db.scalars(select(Observation).where(Observation.expedition_id == e.id))]
    return out


# ------------------------------------------------------------------ observations
class ObservationIn(BaseModel):
    client_uuid: str | None = None
    expedition_id: int | None = None
    mission_id: int | None = None
    taxon_name: str | None = None
    taxon_key: str | None = None
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    accuracy_m: float | None = None
    altitude_m: float | None = None
    coordinate_privacy: Literal["public", "approximate", "private"] | None = None
    observed_at: dt.datetime | None = None
    notes: str = ""
    habitat: str = ""
    microhabitat: str = ""
    temperature_c: float | None = None
    method: str = "visual observation"
    individual_count: int | None = None
    sex: str | None = None
    measurements: dict = {}
    morphology: dict = {}
    observer: str = ""
    ai_suggestion: dict | None = None
    is_demo: bool = False


def obs_out(o: Observation, viewer: User | None) -> dict:
    owner = viewer is not None and viewer.id == o.user_id
    lat, lon, gen = public_coords(o.lat, o.lon, o.coordinate_privacy, is_owner=owner)
    return {
        "id": o.id, "client_uuid": o.client_uuid, "taxon_name": o.taxon_name, "taxon_key": o.taxon_key,
        "id_status": o.id_status, "ai_suggestion": o.ai_suggestion, "lat": lat, "lon": lon,
        "coordinate_display": gen, "accuracy_m": o.accuracy_m, "altitude_m": o.altitude_m,
        "coordinate_privacy": o.coordinate_privacy, "observed_at": o.observed_at.isoformat() if o.observed_at else None,
        "notes": o.notes, "habitat": o.habitat, "microhabitat": o.microhabitat, "temperature_c": o.temperature_c,
        "method": o.method, "individual_count": o.individual_count, "sex": o.sex, "measurements": o.measurements,
        "morphology": o.morphology, "observer": o.observer, "expedition_id": o.expedition_id,
        "mission_id": o.mission_id, "is_demo": o.is_demo, "source": o.source,
        "inat_observation_id": o.inat_observation_id,
        "inat_url": f"{get_settings().inat_web_base}/observations/{o.inat_observation_id}" if o.inat_observation_id else None,
        "photos": [{"id": p.id, "url": f"/api/photos/{p.id}", "kind": p.kind} for p in o.photos],
        "provenance": "DEMO DATA" if o.is_demo else "USER RECORD",
    }


def _create_obs(body: ObservationIn, user: User, db: Session) -> tuple[Observation, list[str], bool]:
    if body.client_uuid:
        existing = db.scalar(select(Observation).where(Observation.client_uuid == body.client_uuid))
        if existing:
            return existing, [], False
    data = body.model_dump(exclude_none=True)
    data["coordinate_privacy"] = body.coordinate_privacy or user.default_coordinate_privacy
    data["observer"] = body.observer or user.display_name or user.username
    o = Observation(user_id=user.id, **data)
    db.add(o)
    db.flush()
    rewards = ["observation"]
    award(db, user, "observation", f"obs:{o.id}")
    if o.habitat and o.microhabitat and o.lat is not None and (o.accuracy_m or 9e9) <= 100:
        award(db, user, "well_documented", f"obs:{o.id}")
        rewards.append("well_documented")
    if o.lat is not None:
        cell = (math.floor(o.lat * 10), math.floor(o.lon * 10))
        others = db.scalars(select(Observation).where(Observation.user_id == user.id, Observation.id != o.id,
                                                      Observation.lat.is_not(None))).all()
        if all((math.floor(x.lat * 10), math.floor(x.lon * 10)) != cell for x in others):
            award(db, user, "new_locality", f"obs:{o.id}")
            rewards.append("new_locality")
    return o, rewards, True


@router.post("/observations")
def create_observation(body: ObservationIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    o, rewards, created = _create_obs(body, user, db)
    db.commit()
    out = obs_out(o, user)
    out["xp_awarded"] = [{"kind": r, "points": XP_RULES[r]} for r in rewards]
    out["created"] = created
    return out


class SyncIn(BaseModel):
    observations: list[ObservationIn]


@router.post("/observations/sync")
def sync_observations(body: SyncIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Idempotent batch upload from the offline queue (dedup by client_uuid)."""
    results = []
    for item in body.observations:
        o, _, created = _create_obs(item, user, db)
        results.append({"client_uuid": item.client_uuid, "id": o.id, "created": created})
    db.commit()
    return {"synced": results}


@router.get("/observations")
def list_observations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [obs_out(o, user) for o in db.scalars(select(Observation).where(Observation.user_id == user.id)
                                                 .order_by(Observation.id.desc()))]


@router.get("/observations/{oid}")
def get_observation(oid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    o = db.get(Observation, oid)
    if not o or o.user_id != user.id:
        raise HTTPException(404)
    return obs_out(o, user)


class ObsPatch(BaseModel):
    taxon_name: str | None = None
    id_status: Literal["needs_identification", "user_identified", "expert_verified"] | None = None
    morphology: dict | None = None
    measurements: dict | None = None
    notes: str | None = None
    coordinate_privacy: Literal["public", "approximate", "private"] | None = None


@router.patch("/observations/{oid}")
def patch_observation(oid: int, body: ObsPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    o = db.get(Observation, oid)
    if not o or o.user_id != user.id:
        raise HTTPException(404)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(o, k, v)
    db.commit()
    return obs_out(o, user)


ALLOWED = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "audio/mpeg": ".mp3",
           "audio/wav": ".wav", "audio/webm": ".webm", "audio/mp4": ".m4a", "audio/ogg": ".ogg"}


@router.post("/observations/{oid}/photos")
async def upload_media(oid: int, file: UploadFile = File(...), user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    o = db.get(Observation, oid)
    if not o or o.user_id != user.id:
        raise HTTPException(404)
    ct = (file.content_type or "").split(";")[0]
    if ct not in ALLOWED:
        raise HTTPException(415, f"Unsupported media type {ct}")
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "File too large (20 MB max)")
    key = get_storage().put(data, ct, ALLOWED[ct])
    p = Photo(observation_id=o.id, storage_key=key, content_type=ct, kind="audio" if ct.startswith("audio") else "photo")
    db.add(p)
    db.commit()
    return {"id": p.id, "url": f"/api/photos/{p.id}", "kind": p.kind}


@router.get("/photos/{pid}")
def get_photo(pid: int, token: str = "", db: Session = Depends(get_db)):
    p = db.get(Photo, pid)
    if not p:
        raise HTTPException(404)
    o = db.get(Observation, p.observation_id)
    uid = decode_token(token) if token else None
    if o.coordinate_privacy == "private" and uid != o.user_id:
        raise HTTPException(403)
    return Response(get_storage().get(p.storage_key), media_type=p.content_type)


@router.post("/ai/suggest")
async def ai_suggest(mode: Literal["live", "demo"] = Form("live"), file: UploadFile | None = File(None),
                     lat: float | None = Form(None), lon: float | None = Form(None)):
    img = await file.read() if file else None
    return get_vision(mode).suggest(img, lat, lon, None)


# ------------------------------------------------------------------ iNaturalist OAuth + submission
@router.get("/inat/status")
def inat_status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    acc = db.scalar(select(ExternalAccount).where(ExternalAccount.user_id == user.id,
                                                  ExternalAccount.provider == "inaturalist"))
    s = get_settings()
    return {"configured": bool(s.inat_client_id and s.inat_client_secret), "connected": bool(acc),
            "login": acc.external_login if acc else None}


@router.get("/inat/oauth/start")
def inat_start(user: User = Depends(current_user)):
    try:
        return {"url": hub.inat.authorize_url(state=create_token(user.id))}
    except UpstreamError as e:
        raise HTTPException(409, e.detail)


@router.get("/inat/oauth/callback")
async def inat_callback(code: str, state: str, db: Session = Depends(get_db)):
    uid = decode_token(state)
    if not uid:
        raise HTTPException(400, "Invalid state")
    s = get_settings()
    try:
        access = await hub.inat.exchange_code(code)
        jwt = await hub.inat.api_jwt(access)
        me = await hub.inat.me(jwt)
    except UpstreamError as e:
        raise HTTPException(502, e.detail)
    acc = db.scalar(select(ExternalAccount).where(ExternalAccount.user_id == uid,
                                                  ExternalAccount.provider == "inaturalist"))
    acc = acc or ExternalAccount(user_id=uid, provider="inaturalist")
    acc.access_token, acc.external_login, acc.external_user_id = access, me.get("login"), str(me.get("id"))
    db.add(acc)
    db.commit()
    return RedirectResponse(f"{s.frontend_origin}/settings?inat=connected")


@router.delete("/inat")
def inat_disconnect(user: User = Depends(current_user), db: Session = Depends(get_db)):
    acc = db.scalar(select(ExternalAccount).where(ExternalAccount.user_id == user.id,
                                                  ExternalAccount.provider == "inaturalist"))
    if acc:
        db.delete(acc)
        db.commit()
    return {"connected": False}


class SubmitIn(BaseModel):
    consent: bool
    license: str = "cc-by-nc"


@router.post("/observations/{oid}/inat-submit")
async def submit_to_inat(oid: int, body: SubmitIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not body.consent:
        raise HTTPException(400, "Explicit consent is required to publish to iNaturalist.")
    o = db.get(Observation, oid)
    if not o or o.user_id != user.id:
        raise HTTPException(404)
    if o.is_demo:
        raise HTTPException(400, "DEMO observations can never be submitted to iNaturalist.")
    if o.inat_observation_id:
        raise HTTPException(409, "Already submitted")
    acc = db.scalar(select(ExternalAccount).where(ExternalAccount.user_id == user.id,
                                                  ExternalAccount.provider == "inaturalist"))
    if not acc:
        raise HTTPException(409, "Connect your iNaturalist account first (Settings).")
    geoprivacy = {"public": "open", "approximate": "obscured", "private": "private"}[o.coordinate_privacy]
    payload = {
        "species_guess": o.taxon_name or "", "observed_on_string": o.observed_at.isoformat(),
        "latitude": o.lat, "longitude": o.lon, "positional_accuracy": o.accuracy_m, "geoprivacy": geoprivacy,
        "description": "\n".join(x for x in [o.notes, f"Habitat: {o.habitat}" if o.habitat else "",
                                              f"Microhabitat: {o.microhabitat}" if o.microhabitat else "",
                                              "Recorded with BIOQUEST"] if x),
    }
    try:
        jwt = await hub.inat.api_jwt(acc.access_token)
        res = await hub.inat.create_observation(jwt, payload)
        inat_id = res.get("id") or (res.get("results") or [{}])[0].get("id")
        storage = get_storage()
        for p in o.photos:
            if p.kind == "photo":
                await hub.inat.upload_photo(jwt, inat_id, os.path.basename(p.storage_key), storage.get(p.storage_key),
                                            p.content_type)
    except UpstreamError as e:
        raise HTTPException(502, e.detail)
    o.inat_observation_id = inat_id
    db.commit()
    return obs_out(o, user)


@router.post("/observations/{oid}/inat-refresh")
async def refresh_inat(oid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Read the community status on iNaturalist; Research Grade earns the 'validation' XP once."""
    o = db.get(Observation, oid)
    if not o or o.user_id != user.id:
        raise HTTPException(404)
    if not o.inat_observation_id:
        raise HTTPException(409, "This observation has not been submitted to iNaturalist.")
    try:
        r = await hub.inat.observation(o.inat_observation_id)
    except UpstreamError as e:
        raise HTTPException(502, e.detail)
    grade = r.get("quality_grade")
    community = (r.get("community_taxon") or r.get("taxon") or {}).get("name")
    awarded = 0
    if grade == "research":
        o.id_status = "research_grade"
        already = db.scalar(select(XPEvent).where(XPEvent.user_id == user.id, XPEvent.kind == "validation",
                                                  XPEvent.ref == f"obs:{o.id}"))
        if not already:
            awarded = award(db, user, "validation", f"obs:{o.id}")
    db.commit()
    return {"quality_grade": grade, "community_taxon": community, "identifications": r.get("identifications_count"),
            "xp_awarded": awarded, "observation": obs_out(o, user), "provenance": "LIVE DATA"}


@router.post("/observations/{oid}/assess")
async def assess_observation(oid: int, range_km: float = 100.0, user: User = Depends(current_user),
                             db: Session = Depends(get_db)):
    """Screen a record against known occurrences and the latest model. Suggestion only."""
    o = db.get(Observation, oid)
    if not o or o.user_id != user.id:
        raise HTTPException(404)
    if o.lat is None or not (o.taxon_key or o.taxon_name):
        raise HTTPException(400, "The observation needs coordinates and a taxon (name or key) to be screened.")
    mode = "demo" if o.is_demo else "live"
    key = o.taxon_key
    if not key:
        found = await hub.search_taxa(o.taxon_name, mode)
        exact = [t for t in found["results"] if t["scientific_name"].lower() == o.taxon_name.lower()]
        if not exact:
            raise HTTPException(404 if not found["errors"] else 502,
                                {"message": f"Taxon '{o.taxon_name}' not found in the sources.",
                                 "errors": found["errors"]})
        key = exact[0]["key"]
    from .core import qc_occurrences

    data, _ = await qc_occurrences(key, mode, [])
    valid = [r for r in data["records"] if r.qc_status == "VALID" and r.lat is not None
             and not (o.inat_observation_id and r.inat_observation_id == str(o.inat_observation_id))]
    known = [{"lat": r.lat, "lon": r.lon} for r in valid]
    env = get_provider("demo") if mode == "demo" else get_provider("worldclim")
    if known and o.altitude_m is not None and env.available()[0]:
        try:
            lats, lons = [k["lat"] for k in known], [k["lon"] for k in known]
            res = 0.05 if mode == "demo" else 0.1667
            g = Grid([min(lons) - res, min(lats) - res, max(lons) + res, max(lats) + res], res)
            el = env.grid(g, ["elev"])["elev"]
            rr, cc, ins = g.index(lats, lons)
            for k, a, b, i in zip(known, rr, cc, ins):
                if i and math.isfinite(float(el[a, b])):
                    k["elevation_m"] = float(el[a, b])
        except NotConfigured:
            pass
    model = None
    t = data["taxon"]
    keys = set(data["keys"].values()) | {key}
    run = db.scalar(select(ModelRun).where(ModelRun.taxon_key.in_(keys), ModelRun.status == "completed")
                    .order_by(ModelRun.id.desc()))
    if run:
        p = db.scalar(select(Prediction).where(Prediction.model_run_id == run.id, Prediction.algorithm == "ensemble"))
        if p:
            model = {"grid": p.grid, "threshold": p.threshold, "run_id": run.id, "provenance": run.provenance}
    out = assess(o.lat, o.lon, o.altitude_m, known, model, range_km)
    out["taxon"] = {"key": key, "scientific_name": t.scientific_name}
    out["known_records_provenance"] = data.get("provenance")
    out["errors"] = data["errors"]
    return out


# ------------------------------------------------------------------ projects (collaboration)
class ProjectIn(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    description: str = ""


def _project_access(pid: int, user: User, db: Session) -> Project:
    p = db.get(Project, pid)
    if not p or (p.owner_id != user.id and user.id not in (p.members or [])):
        raise HTTPException(404)
    return p


def project_out(p: Project, user: User, db: Session, full: bool = False) -> dict:
    ids = [p.owner_id] + [m for m in (p.members or []) if m != p.owner_id]
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))}
    shared = db.scalars(select(ProjectObservation).where(ProjectObservation.project_id == p.id)
                        .order_by(ProjectObservation.id.desc())).all()
    out = {"id": p.id, "name": p.name, "description": p.description, "is_owner": p.owner_id == user.id,
           "members": [{"id": i, "username": users[i].username, "role": "owner" if i == p.owner_id else "member"}
                       for i in ids if i in users],
           "n_observations": len(shared), "created_at": p.created_at.isoformat()}
    if full:
        obs = []
        for s in shared:
            o = db.get(Observation, s.observation_id)
            if o:
                item = obs_out(o, user)  # privacy applied: non-owners get generalised coordinates
                item["shared_by"] = users[s.shared_by].username if s.shared_by in users else None
                obs.append(item)
        out["observations"] = obs
    return out


@router.post("/projects")
def create_project(body: ProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = Project(name=body.name, description=body.description, owner_id=user.id, members=[])
    db.add(p)
    db.commit()
    return project_out(p, user, db)


@router.get("/projects")
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ps = [p for p in db.scalars(select(Project).order_by(Project.id.desc()))
          if p.owner_id == user.id or user.id in (p.members or [])]
    return [project_out(p, user, db) for p in ps]


@router.get("/projects/{pid}")
def get_project(pid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return project_out(_project_access(pid, user, db), user, db, full=True)


class MemberIn(BaseModel):
    username: str


@router.post("/projects/{pid}/members")
def add_member(pid: int, body: MemberIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _project_access(pid, user, db)
    if p.owner_id != user.id:
        raise HTTPException(403, "Only the project owner can add members.")
    u = db.scalar(select(User).where(User.username == body.username))
    if not u:
        raise HTTPException(404, f"No BIOQUEST user '{body.username}'.")
    if u.id != p.owner_id and u.id not in (p.members or []):
        p.members = [*(p.members or []), u.id]
    db.commit()
    return project_out(p, user, db)


class ShareIn(BaseModel):
    observation_id: int


@router.post("/projects/{pid}/observations")
def share_observation(pid: int, body: ShareIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _project_access(pid, user, db)
    o = db.get(Observation, body.observation_id)
    if not o or o.user_id != user.id:
        raise HTTPException(404, "You can only share your own observations.")
    exists = db.scalar(select(ProjectObservation).where(ProjectObservation.project_id == p.id,
                                                        ProjectObservation.observation_id == o.id))
    if not exists:
        db.add(ProjectObservation(project_id=p.id, observation_id=o.id, shared_by=user.id))
        db.commit()
    return project_out(p, user, db, full=True)


# ------------------------------------------------------------------ discoveries
class DiscoveryIn(BaseModel):
    observation_id: int
    category: Literal["new_local_record", "range_extension", "rare_observation", "taxonomically_unresolved",
                      "potentially_undescribed"]
    evidence_level: int = Field(0, ge=0, le=5)
    rationale: str = ""


@router.get("/discoveries/meta")
def discoveries_meta():
    return {"categories": DISCOVERY_CATEGORIES, "evidence_levels": EVIDENCE_LEVELS, "record_flags": RECORD_FLAGS,
            "disclaimer": NEW_SPECIES_DISCLAIMER,
            "note": "Working classification only — NOT a scientific certification."}


def disc_out(d: Discovery) -> dict:
    return {"id": d.id, "observation_id": d.observation_id, "category": d.category,
            "category_label": DISCOVERY_CATEGORIES[d.category], "evidence_level": d.evidence_level,
            "evidence_label": EVIDENCE_LEVELS[d.evidence_level], "rationale": d.rationale,
            "review_status": d.review_status, "is_demo": d.is_demo, "created_at": d.created_at.isoformat()}


@router.post("/discoveries")
def create_discovery(body: DiscoveryIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    o = db.get(Observation, body.observation_id)
    if not o or o.user_id != user.id:
        raise HTTPException(404)
    # Self-reported discoveries are capped at level 3; levels 4–5 need expert review (not automated).
    level = min(body.evidence_level, 3)
    if body.category == "potentially_undescribed" and not body.rationale.strip():
        raise HTTPException(400, "A rationale (diagnostic characters, comparisons) is required for this category.")
    d = Discovery(user_id=user.id, observation_id=o.id, category=body.category, evidence_level=level,
                  rationale=body.rationale, is_demo=o.is_demo)
    db.add(d)
    db.commit()
    out = disc_out(d)
    if body.evidence_level > 3:
        out["note"] = "Evidence levels 4–5 require review by a taxonomic specialist; stored as level 3."
    return out


@router.get("/discoveries")
def list_discoveries(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [disc_out(d) for d in db.scalars(select(Discovery).where(Discovery.user_id == user.id)
                                            .order_by(Discovery.id.desc()))]


# ------------------------------------------------------------------ profile
@router.get("/profile")
def profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    obs = db.scalars(select(Observation).where(Observation.user_id == user.id)).all()
    xp = db.scalars(select(XPEvent).where(XPEvent.user_id == user.id).order_by(XPEvent.id.desc()).limit(30)).all()
    localities = {(round(o.lat, 1), round(o.lon, 1)) for o in obs if o.lat is not None}
    level = int(math.sqrt(user.xp / 50)) + 1
    return {
        "user": {"id": user.id, "username": user.username, "display_name": user.display_name, "xp": user.xp,
                 "level": level, "next_level_xp": 50 * level ** 2},
        "stats": {
            "observations": len(obs),
            "species": len({o.taxon_name for o in obs if o.taxon_name}),
            "localities": len(localities),
            "photos": sum(len(o.photos) for o in obs),
            "expeditions": db.scalar(select(func.count(Expedition.id)).where(Expedition.user_id == user.id)),
            "missions_completed": db.scalar(select(func.count(Mission.id)).where(
                Mission.user_id == user.id, Mission.status == "completed")),
            "discoveries": db.scalar(select(func.count(Discovery.id)).where(Discovery.user_id == user.id)),
            "demo_records": sum(1 for o in obs if o.is_demo),
        },
        "recent_observations": [obs_out(o, user) for o in sorted(obs, key=lambda x: -x.id)[:12]],
        "xp_events": [{"kind": e.kind, "points": e.points, "at": e.created_at.isoformat()} for e in xp],
        "xp_rules": XP_RULES,
    }


# ------------------------------------------------------------------ compare
@router.get("/compare")
async def compare(keys: str, mode: Literal["live", "demo"] = "live", user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    out = []
    for k in [x for x in keys.split(",") if x][:4]:
        t, kk, errors = await hub.resolve_counterparts(k, mode)
        if not t:
            out.append({"key": k, "error": errors})
            continue
        mine = db.scalars(select(Observation).where(Observation.user_id == user.id,
                                                    Observation.taxon_name == t.scientific_name)).all()
        meas: dict[str, list] = {}
        for o in mine:
            for mk, mv in (o.measurements or {}).items():
                if isinstance(mv, (int, float)):
                    meas.setdefault(mk, []).append(mv)
        out.append({
            "key": k, "taxon": t.to_dict(),
            "your_observations": len(mine),
            "your_measurements": {mk: {"n": len(v), "min": min(v), "max": max(v), "mean": round(sum(v) / len(v), 2)}
                                  for mk, v in meas.items()},
            "your_morphology_notes": [o.morphology for o in mine if o.morphology],
            "literature": ({"status": "demo", "items": [], "provenance": "DEMO DATA",
                            "note": "DEMO taxa are fictitious: there is no literature about them."} if mode == "demo"
                           else await get_literature().search(t.scientific_name,
                                                              (kk.get("gbif") or ":").split(":")[1] or None)),
            "errors": errors,
        })
    return {"taxa": out, "provenance": "DEMO DATA" if mode == "demo" else "LIVE DATA"}


# ------------------------------------------------------------------ admin
@router.get("/admin/overview")
def admin_overview(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role != "admin":
        raise HTTPException(403, "Admin only")
    from ..models import Occurrence

    return {
        "users": db.scalar(select(func.count(User.id))),
        "observations": db.scalar(select(func.count(Observation.id))),
        "occurrences_cached": db.scalar(select(func.count(Occurrence.id))),
        "occurrences_by_qc": dict(db.execute(select(Occurrence.qc_status, func.count(Occurrence.id))
                                             .group_by(Occurrence.qc_status)).all()),
        "model_runs": [{"id": r.id, "taxon": r.scientific_name, "status": r.status, "provenance": r.provenance,
                        "n_used": r.n_occurrences_used, "env": r.env_provider, "created_at": r.created_at.isoformat()}
                       for r in db.scalars(select(ModelRun).order_by(ModelRun.id.desc()).limit(20))],
    }
