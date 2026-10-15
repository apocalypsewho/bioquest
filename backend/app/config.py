"""Runtime configuration (environment variables, see .env.example)."""
import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BIOQUEST_", extra="ignore")

    # Database: SQLite by default (zero setup). Use postgresql+psycopg://... for PostgreSQL/PostGIS.
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'bioquest.db'}"

    # Secret used to sign session tokens. CHANGE IN PRODUCTION.
    secret_key: str = "dev-only-change-me"
    token_ttl_hours: int = 24 * 14

    # Identify the app to iNaturalist / GBIF (both ask for a descriptive User-Agent).
    user_agent: str = "BIOQUEST/0.1 (biodiversity exploration MVP; contact: set BIOQUEST_CONTACT_EMAIL)"
    contact_email: str = ""

    # iNaturalist OAuth application (https://www.inaturalist.org/oauth/applications/new)
    inat_client_id: str = ""
    inat_client_secret: str = ""
    inat_redirect_uri: str = "http://localhost:8000/api/inat/oauth/callback"
    inat_api_base: str = "https://api.inaturalist.org/v1"
    inat_web_base: str = "https://www.inaturalist.org"
    # iNaturalist recommends ~1 request/second and <= 60/minute.
    inat_min_interval_s: float = 1.0

    gbif_api_base: str = "https://api.gbif.org/v1"

    # Environmental data. "demo" (synthetic, labelled DEMO) or "worldclim" (local GeoTIFFs).
    env_provider: str = "demo"
    worldclim_dir: str = str(BASE_DIR / "data" / "worldclim")
    landcover_dir: str = str(BASE_DIR / "data" / "worldcover")
    # OpenStreetMap Overpass API for distance to roads/trails (https://wiki.openstreetmap.org/wiki/Overpass_API)
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    crossref_api_base: str = "https://api.crossref.org"

    # Where uploaded photos/audio go (local disk in MVP; S3 adapter in app/services/storage.py)
    storage_dir: str = str(BASE_DIR / "data" / "uploads")
    storage_backend: str = "local"
    s3_bucket: str = ""
    s3_endpoint_url: str = ""

    frontend_origin: str = "http://localhost:3000"
    http_timeout_s: float = 30.0


def _adapt(s: Settings) -> Settings:
    # Managed Postgres URLs (Render, Heroku…) use postgres:// — SQLAlchemy needs the psycopg driver name.
    for prefix in ("postgres://", "postgresql://"):
        if s.database_url.startswith(prefix):
            s.database_url = "postgresql+psycopg://" + s.database_url[len(prefix):]
    # On Render the public HTTPS URL is known at runtime: frontend and OAuth callback share that origin.
    ext = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    if ext:
        if "BIOQUEST_FRONTEND_ORIGIN" not in os.environ:
            s.frontend_origin = ext
        if "BIOQUEST_INAT_REDIRECT_URI" not in os.environ:
            s.inat_redirect_uri = f"{ext}/api/inat/oauth/callback"
    return s


@lru_cache
def get_settings() -> Settings:
    return _adapt(Settings())
