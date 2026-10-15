from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db
from .routers import core, field, modeling

app = FastAPI(title="BIOQUEST API", version="0.1.0",
              description="Discover what hasn't been mapped yet. Biodiversity exploration backend.")
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.frontend_origin.split(",") if o.strip()]
    + ["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(core.router)
app.include_router(modeling.router)
app.include_router(field.router)


@app.on_event("startup")
def _startup():
    init_db()
