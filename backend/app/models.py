"""Relational schema (SQLAlchemy 2.0).

Coordinates are stored as plain lat/lon (WGS84, EPSG:4326) so the same schema runs on SQLite
and PostgreSQL. On PostGIS, `scripts/postgis_upgrade.sql` adds geography columns + GiST indexes
derived from these fields.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16), default="user")  # user | admin
    xp: Mapped[int] = mapped_column(Integer, default=0)
    default_coordinate_privacy: Mapped[str] = mapped_column(String(16), default="approximate")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)

    observations: Mapped[list["Observation"]] = relationship(back_populates="user")


class ExternalAccount(Base):
    """OAuth link to an external service (iNaturalist). Tokens never leave the backend."""

    __tablename__ = "external_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32))  # "inaturalist"
    external_user_id: Mapped[Optional[str]] = mapped_column(String(64))
    external_login: Mapped[Optional[str]] = mapped_column(String(128))
    access_token: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("user_id", "provider"),)


class ExternalSource(Base):
    """Registry of data sources (iNaturalist, GBIF, WorldClim, DEMO...) with citation/terms."""

    __tablename__ = "external_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(String(256), default="")
    terms_url: Mapped[str] = mapped_column(String(256), default="")
    citation: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    members: Mapped[list] = mapped_column(JSON, default=list)  # user ids (collaboration: MVP 3)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProjectObservation(Base):
    """Observation shared into a collaborative project (members see it with privacy rules applied)."""

    __tablename__ = "project_observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("observations.id"), index=True)
    shared_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Taxon(Base):
    """Local cache of a taxon. `source` + `source_id` identify where it came from."""

    __tablename__ = "taxa"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(16))  # inaturalist | gbif | demo | user
    source_id: Mapped[str] = mapped_column(String(64))
    scientific_name: Mapped[str] = mapped_column(String(256), index=True)
    rank: Mapped[str] = mapped_column(String(32), default="")
    common_name: Mapped[Optional[str]] = mapped_column(String(256))
    classification: Mapped[dict] = mapped_column(JSON, default=dict)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("source", "source_id"),)


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256), default="")
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    elevation_m: Mapped[Optional[float]] = mapped_column(Float)
    country_code: Mapped[Optional[str]] = mapped_column(String(2))


class Occurrence(Base):
    """External occurrence record (GBIF / iNaturalist / DEMO), stored with its QC verdict.

    Records are never deleted by QC: `qc_status` is VALID / QUESTIONABLE / EXCLUDED with reasons.
    """

    __tablename__ = "occurrences"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(16), index=True)  # gbif | inaturalist | demo
    source_record_id: Mapped[str] = mapped_column(String(64))
    taxon_key: Mapped[str] = mapped_column(String(64), index=True)  # e.g. "inat:12345"
    scientific_name: Mapped[str] = mapped_column(String(256))
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lon: Mapped[Optional[float]] = mapped_column(Float)
    uncertainty_m: Mapped[Optional[float]] = mapped_column(Float)
    event_date: Mapped[Optional[str]] = mapped_column(String(32))
    basis_of_record: Mapped[Optional[str]] = mapped_column(String(64))
    institution: Mapped[Optional[str]] = mapped_column(String(256))
    recorded_by: Mapped[Optional[str]] = mapped_column(String(256))
    country_code: Mapped[Optional[str]] = mapped_column(String(2))
    url: Mapped[Optional[str]] = mapped_column(String(512))
    qc_status: Mapped[str] = mapped_column(String(16), default="VALID")
    qc_reasons: Mapped[list] = mapped_column(JSON, default=list)
    duplicate_of: Mapped[Optional[str]] = mapped_column(String(96))
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("source", "source_record_id"),)


class Expedition(Base):
    __tablename__ = "expeditions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    mission_id: Mapped[Optional[int]] = mapped_column(ForeignKey("missions.id"))
    name: Mapped[str] = mapped_column(String(256), default="")
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    ended_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    route: Mapped[list] = mapped_column(JSON, default=list)  # [[lon, lat, iso_time], ...] private
    distance_km: Mapped[float] = mapped_column(Float, default=0.0)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class Mission(Base):
    __tablename__ = "missions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    target_taxon_key: Mapped[Optional[str]] = mapped_column(String(64))
    target_name: Mapped[Optional[str]] = mapped_column(String(256))
    objective: Mapped[str] = mapped_column(Text)
    center_lat: Mapped[float] = mapped_column(Float)
    center_lon: Mapped[float] = mapped_column(Float)
    radius_m: Mapped[float] = mapped_column(Float)
    area_km2: Mapped[float] = mapped_column(Float)
    distance_km: Mapped[Optional[float]] = mapped_column(Float)
    priority: Mapped[Optional[dict]] = mapped_column(JSON)  # ExplorationPriorityScore breakdown
    zone: Mapped[dict] = mapped_column(JSON, default=dict)  # full zone payload + provenance
    model_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("model_runs.id"))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | completed | abandoned
    provenance: Mapped[str] = mapped_column(String(16), default="LIVE")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Observation(Base):
    """A field record made by a BIOQUEST user."""

    __tablename__ = "observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_uuid: Mapped[Optional[str]] = mapped_column(String(64), unique=True)  # offline sync idempotency
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expedition_id: Mapped[Optional[int]] = mapped_column(ForeignKey("expeditions.id"))
    mission_id: Mapped[Optional[int]] = mapped_column(ForeignKey("missions.id"))
    source: Mapped[str] = mapped_column(String(16), default="user")
    taxon_name: Mapped[Optional[str]] = mapped_column(String(256))
    taxon_key: Mapped[Optional[str]] = mapped_column(String(64))
    id_status: Mapped[str] = mapped_column(String(32), default="needs_identification")
    ai_suggestion: Mapped[Optional[dict]] = mapped_column(JSON)
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lon: Mapped[Optional[float]] = mapped_column(Float)
    accuracy_m: Mapped[Optional[float]] = mapped_column(Float)
    altitude_m: Mapped[Optional[float]] = mapped_column(Float)
    coordinate_privacy: Mapped[str] = mapped_column(String(16), default="approximate")
    observed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    notes: Mapped[str] = mapped_column(Text, default="")
    habitat: Mapped[str] = mapped_column(String(256), default="")
    microhabitat: Mapped[str] = mapped_column(String(256), default="")
    temperature_c: Mapped[Optional[float]] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(128), default="visual observation")
    individual_count: Mapped[Optional[int]] = mapped_column(Integer)
    sex: Mapped[Optional[str]] = mapped_column(String(32))
    measurements: Mapped[dict] = mapped_column(JSON, default=dict)
    morphology: Mapped[dict] = mapped_column(JSON, default=dict)
    observer: Mapped[str] = mapped_column(String(128), default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    inat_observation_id: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)

    user: Mapped[User] = relationship(back_populates="observations")
    photos: Mapped[list["Photo"]] = relationship(back_populates="observation", cascade="all, delete-orphan")


class Photo(Base):
    __tablename__ = "photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("observations.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(64), default="image/jpeg")
    kind: Mapped[str] = mapped_column(String(16), default="photo")  # photo | audio
    license: Mapped[str] = mapped_column(String(32), default="cc-by-nc")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    observation: Mapped[Observation] = relationship(back_populates="photos")


class EnvironmentalData(Base):
    """Registry of environmental layers available to the modelling service."""

    __tablename__ = "environmental_data"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(32))
    variable: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(String(256), default="")
    units: Mapped[str] = mapped_column(String(32), default="")
    resolution: Mapped[str] = mapped_column(String(64), default="")
    path: Mapped[Optional[str]] = mapped_column(String(512))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class ModelRun(Base):
    __tablename__ = "model_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    taxon_key: Mapped[str] = mapped_column(String(64), index=True)
    scientific_name: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32))  # completed | insufficient_data | failed
    provenance: Mapped[str] = mapped_column(String(32))  # MODEL OUTPUT (LIVE input) / (DEMO input)
    env_provider: Mapped[str] = mapped_column(String(32))
    variables: Mapped[list] = mapped_column(JSON, default=list)
    resolution_deg: Mapped[float] = mapped_column(Float)
    bbox: Mapped[list] = mapped_column(JSON, default=list)
    n_occurrences_raw: Mapped[int] = mapped_column(Integer, default=0)
    n_occurrences_used: Mapped[int] = mapped_column(Integer, default=0)
    n_background: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    qc_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Prediction(Base):
    """Gridded output of one algorithm (or the ensemble) for a ModelRun."""

    __tablename__ = "predictions"
    id: Mapped[int] = mapped_column(primary_key=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id"), index=True)
    algorithm: Mapped[str] = mapped_column(String(32))  # maxent | random_forest | glm | ensemble | agreement
    grid: Mapped[dict] = mapped_column(JSON)  # {bbox, width, height, values (row-major, north first), nodata}
    threshold: Mapped[Optional[float]] = mapped_column(Float)


class Discovery(Base):
    """Working classification of an interesting record. NOT a scientific certification."""

    __tablename__ = "discoveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("observations.id"))
    category: Mapped[str] = mapped_column(String(48))
    evidence_level: Mapped[int] = mapped_column(Integer, default=0)
    rationale: Mapped[str] = mapped_column(Text, default="")
    review_status: Mapped[str] = mapped_column(String(32), default="self_reported")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class XPEvent(Base):
    __tablename__ = "xp_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(48))
    points: Mapped[int] = mapped_column(Integer)
    ref: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
