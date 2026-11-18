import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.cache import LRUCache
from app.clicks import ClickRecorder
from app.codegen import CodeGenerator
from app.config import Settings, get_settings
from app.db import Base, make_engine, make_session_factory
from app.errors import AppError
from app.geo import build_geo_resolver
from app import models  # noqa: F401  (register tables)
from app.ratelimit import TokenBucketLimiter
from app.routes_api import router as api_router
from app.routes_redirect import router as redirect_router
from app.service import LinkService

log = logging.getLogger("urlshortener")

DESCRIPTION = """
Scalable URL shortener with persistent storage and click analytics.

* Management endpoints (`/api/v1/links*`) need an `X-API-Key` header.
* `GET /{code}` is public and answers `302` (every click is counted).
* Errors use `{"error": {"code": "...", "message": "..."}}`.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app with its engine, cache, click recorder, limiter, service and routes."""
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    cache = LRUCache(settings.cache_max_entries, settings.cache_ttl_seconds)
    recorder = ClickRecorder(
        session_factory,
        build_geo_resolver(settings.geoip_db_path),
        settings.secret_key,
        queue_size=settings.click_queue_size,
        batch_size=settings.click_batch_size,
        flush_interval=settings.click_flush_interval,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Create tables and start the click recorder on startup; stop it and dispose the engine on shutdown."""
        Base.metadata.create_all(engine)
        recorder.start()
        yield
        recorder.stop()
        engine.dispose()

    app = FastAPI(title="URL Shortener", version="1.0.0", description=DESCRIPTION, lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.cache = cache
    app.state.recorder = recorder
    app.state.limiter = TokenBucketLimiter(settings.rate_limit_per_minute, settings.rate_limit_burst)
    app.state.links = LinkService(settings, CodeGenerator(settings.secret_key), cache)

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        """Render an AppError as the standard JSON error envelope."""
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status_code, headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        """Render request validation failures as a 422 JSON error envelope."""
        detail = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'] if p != 'body')}: {e['msg']}" for e in exc.errors()
        )
        return JSONResponse({"error": {"code": "validation_error", "message": detail}}, status_code=422)

    # API routes first so /api/... and /healthz win over the catch-all /{code}.
    app.include_router(api_router)
    app.include_router(redirect_router)
    return app


def app_factory() -> FastAPI:
    """uvicorn --factory entry point."""
    return create_app()
