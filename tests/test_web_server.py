"""Tests for the pages HTTP server."""

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, TestClient, TestServer

from bot.web import create_app


@pytest.fixture
def pages_dir(tmp_path):
    """Create a temp pages directory with a sample file."""
    page = tmp_path / "test123.html"
    page.write_text("<h1>Test Page</h1>", encoding="utf-8")
    return tmp_path


@pytest.mark.asyncio
async def test_serves_existing_page(pages_dir, monkeypatch):
    """GET /pages/<file>.html returns the HTML content."""
    monkeypatch.setattr("bot.web.PAGES_DIR", pages_dir)

    app = create_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/pages/test123.html")
        assert resp.status == 200
        text = await resp.text()
        assert "<h1>Test Page</h1>" in text


@pytest.mark.asyncio
async def test_404_for_missing_page(pages_dir, monkeypatch):
    """GET /pages/<missing>.html returns 404."""
    monkeypatch.setattr("bot.web.PAGES_DIR", pages_dir)

    app = create_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/pages/nonexistent.html")
        assert resp.status == 404


@pytest.mark.asyncio
async def test_rejects_path_traversal(pages_dir, monkeypatch):
    """Path traversal attempts return 404."""
    monkeypatch.setattr("bot.web.PAGES_DIR", pages_dir)

    app = create_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/pages/..%2F..%2Fetc%2Fpasswd")
        assert resp.status == 404
