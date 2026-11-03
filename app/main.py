"""PodLens FastAPI application entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.config import get_settings
from app.core.exceptions import PodLensError
from app.core.logging_config import configure_logging
from app.database.connection import init_db

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("PodLens started. YouTube configured: %s. LLM configured: %s.",
                settings.youtube_configured, settings.llm_configured)
    if not settings.youtube_configured:
        logger.warning("YOUTUBE_API_KEY not set - video/comment collection is disabled.")
    if not settings.llm_configured:
        logger.warning("LLM_API_KEY not set - audience insight generation is disabled.")
    yield


app = FastAPI(
    title="PodLens",
    description="Intelligent YouTube Podcast Analyzer for Audience Insights",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(PodLensError)
async def podlens_error_handler(request: Request, exc: PodLensError):
    logger.warning("Domain error on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=400, content={"detail": str(exc)})


app.include_router(api_router, prefix="/api")

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
