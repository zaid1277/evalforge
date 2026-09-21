import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import config as config_api
from app.api import evaluation_cases, evaluations, export, generation, health, projects, sources
from app.config import settings

# Plain stdlib logging is enough for a student-scale project -- no need
# for a dedicated observability stack. Never log secrets (see config.py).
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is managed by Alembic migrations as of M6 (see api/alembic/),
    # not by calling Base.metadata.create_all() here. Run `alembic upgrade
    # head` (from api/) before starting the app -- see README setup.
    yield


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# Allow the Next.js frontend (running on a different port/origin) to call
# this API from the browser during local development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Content-Disposition isn't on the CORS response-header safelist, so
    # without this the browser silently hides it from fetch()'s response.headers
    # -- the M8 export download would always fall back to a generic filename.
    expose_headers=["Content-Disposition"],
)

app.include_router(health.router)
app.include_router(projects.router)
app.include_router(sources.router)
app.include_router(generation.router)
app.include_router(evaluation_cases.router)
app.include_router(export.router)
app.include_router(evaluations.router)
app.include_router(config_api.router)
