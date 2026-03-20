"""Lightweight HTTP server for serving published AS-IS pages."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

from aiohttp import web

from bot.config import PAGES_BASE_URL, PAGES_DIR

logger = logging.getLogger(__name__)


def _parse_port() -> int:
    """Extract port from PAGES_BASE_URL (default 8080)."""
    parsed = urlparse(PAGES_BASE_URL)
    return parsed.port or 8080


def _parse_prefix() -> str:
    """Extract URL path prefix from PAGES_BASE_URL (e.g. '/pages')."""
    parsed = urlparse(PAGES_BASE_URL)
    # Strip trailing slash for clean join
    return parsed.path.rstrip("/") or "/pages"


async def _handle_page(request: web.Request) -> web.Response:
    """Serve a static HTML file from PAGES_DIR."""
    filename = request.match_info["filename"]

    # Security: only allow simple filenames (no path traversal)
    if "/" in filename or "\\" in filename or ".." in filename:
        raise web.HTTPNotFound()

    filepath = PAGES_DIR / filename
    if not filepath.is_file():
        raise web.HTTPNotFound()

    return web.FileResponse(filepath)


def create_app() -> web.Application:
    """Create an aiohttp app that serves pages."""
    app = web.Application()
    prefix = _parse_prefix()
    app.router.add_get(f"{prefix}/{{filename}}", _handle_page)
    return app


async def start_web_server() -> web.AppRunner:
    """Start the HTTP server in the background. Returns the runner."""
    PAGES_DIR.mkdir(parents=True, exist_ok=True)

    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()

    port = _parse_port()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logger.info("Pages HTTP server started on port %d", port)
    return runner
