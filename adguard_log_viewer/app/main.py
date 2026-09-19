"""FastAPI application factory and entry point.

Serves the JSON API under ``/api`` and the built frontend from ``app/static``.
Under Home Assistant ingress the whole app is reachable at a dynamic prefix, so
the frontend uses relative asset URLs and hash routing and nothing here needs to
know the prefix.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.router import api_router
from app.common.timeutil import now_ns
from app.config import Settings, get_settings
from app.db.database import Database, QueryTimeout, set_database
from app.filters.nodes import FilterError
from app.i18n import (
    Message,
    detail_of,
    localize,
    reset_current_language,
    resolve_language,
    set_current_language,
)
from app.ingest.ingestor import Ingestor
from app.logging_setup import setup_logging
from app.runtime import AppState
from app.services.settings_service import SettingsError

_LOGGER = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"

PLACEHOLDER_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>AdGuard Log Viewer</title>
<style>body{font-family:system-ui,sans-serif;margin:3rem auto;max-width:44rem;line-height:1.6;
color:#1c1c1c;background:#fafafa}code{background:#eee;padding:.15rem .35rem;border-radius:4px}
</style></head><body>
<h1>AdGuard Log Viewer</h1>
<p>The backend is running, but no frontend build was found.</p>
<p>Build it with <code>npm install &amp;&amp; npm run build</code> in the
<code>frontend</code> directory, or open the API docs at <code>/docs</code>.</p>
</body></html>"""


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    database = Database(settings.db_path)
    state = AppState(settings=settings, db=database)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        _LOGGER.info("AdGuard Log Viewer %s starting", __version__)
        state.started_at_ns = now_ns()
        state.init_database()
        set_database(database)
        await state.init_provider()

        ingestor = Ingestor(state)
        state.ingestor = ingestor
        application.state.app_state = state
        if settings.ingest_enabled:
            ingestor.start()
        else:
            _LOGGER.warning("Ingest is disabled by configuration")
        state.prime_provider_status()

        try:
            yield
        finally:
            _LOGGER.info("Shutting down")
            await ingestor.stop()
            await state.shutdown()
            set_database(None)

    application = FastAPI(
        title="AdGuard Log Viewer",
        description="DNS query log viewer and analyzer for AdGuard Home on Home Assistant.",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )
    application.state.app_state = state

    @application.middleware("http")
    async def _language(request: Request, call_next: Any) -> Response:
        """Pin the request's language for the messages the backend produces.

        The frontend sends the language it is rendering in ``Accept-Language``,
        which already reflects both Home Assistant's language and any override
        the user picked on the Settings page. A browser hitting the API directly
        sends its own list, which is the right answer for it too.
        """
        token = set_current_language(resolve_language(request.headers.get("accept-language")))
        try:
            return await call_next(request)
        finally:
            reset_current_language(token)

    def _error(err: Exception) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(localize(detail_of(err)))})

    @application.exception_handler(FilterError)
    async def _filter_error(_: Request, err: FilterError) -> JSONResponse:
        return _error(err)

    @application.exception_handler(QueryTimeout)
    async def _query_timeout(_: Request, err: QueryTimeout) -> JSONResponse:
        return _error(err)

    @application.exception_handler(SettingsError)
    async def _settings_error(_: Request, err: SettingsError) -> JSONResponse:
        return _error(err)

    @application.exception_handler(HTTPException)
    async def _http_error(_: Request, err: HTTPException) -> JSONResponse:
        """FastAPI's own handler, with the detail translated on the way out."""
        return JSONResponse(
            status_code=err.status_code,
            content={"detail": localize(err.detail)},
            headers=err.headers,
        )

    application.include_router(api_router)

    assets_dir = STATIC_DIR / "assets"
    if assets_dir.is_dir():
        application.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @application.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> Response:
        """Serve the single-page app, falling back to ``index.html``."""
        if path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": str(Message("Not found"))})

        candidate = (STATIC_DIR / path).resolve() if path else INDEX_FILE
        if (
            path
            and STATIC_DIR.resolve() in candidate.parents
            and candidate.is_file()
        ):
            return FileResponse(candidate)
        if INDEX_FILE.is_file():
            return FileResponse(INDEX_FILE, headers={"Cache-Control": "no-cache"})
        return Response(content=PLACEHOLDER_PAGE, media_type="text/html")

    return application


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_config=None,
        access_log=settings.debug,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
