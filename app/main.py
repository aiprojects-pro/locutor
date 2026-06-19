"""Aplicación FastAPI: carga del modelo, middlewares, rutas y manejo de errores.

IMPORTANTE: ejecutar como UN ÚNICO proceso uvicorn (sin --workers). El modelo,
el pool de concurrencia y el rate limiter son estado global en memoria; el
rendimiento se escala con concurrencia async interna, no con varios procesos.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import routes_api, routes_web
from app.config import get_settings
from app.db.session import init_db
from app.jobs import JobManager
from app.logging_conf import configure_logging, get_logger
from app.security.headers import SecurityHeadersMiddleware
from app.tts.engine import VoiceRegistry, load_voices
from app.tts.normalize import load_normalizer

settings = get_settings()
configure_logging()
logger = get_logger("locutor.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings.work_dir.mkdir(parents=True, exist_ok=True)

    normalizer = load_normalizer(settings.normalization_config)
    voices, default_voice = load_voices(settings)
    engine = VoiceRegistry(settings, voices, default_voice)
    engine.load()  # carga única + warm-up de cada modelo; lanza si falta alguno

    app.state.settings = settings
    app.state.engine = engine
    app.state.normalizer = normalizer
    app.state.jobs = JobManager(settings, engine, normalizer)
    logger.info("aplicación lista", extra={"event": "startup", "status": "ready"})
    try:
        yield
    finally:
        app.state.jobs.shutdown()
        logger.info("aplicación detenida", extra={"event": "shutdown"})


app = FastAPI(title="Locutor TTS", lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(SecurityHeadersMiddleware)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(routes_api.router)
app.include_router(routes_web.router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # Para páginas web, redirige al login en 401; para API/JSON, responde JSON.
    accepts_html = "text/html" in request.headers.get("accept", "")
    if exc.status_code == 401 and accepts_html and not request.url.path.startswith("/api"):
        return RedirectResponse("/login", status_code=302)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
