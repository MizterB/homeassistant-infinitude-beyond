"""Shared fixtures for the Infinitude Beyond test suite.

Layer 1 tests exercise the vendored ``infinitude`` API client in isolation,
with no Home Assistant dependency. Instead of mocking aiohttp internals (which
is fragile across aiohttp versions), we run a real in-process ``aiohttp`` test
server that serves synthetic, PII-free JSON fixtures shaped like a real v1.7
system, and point the client at it over real HTTP.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

# Make the vendored API client importable as a top-level ``infinitude`` package
# WITHOUT importing custom_components/infinitude_beyond/__init__.py, which depends
# on `homeassistant`. This keeps Layer 1 fully HA-free.
CLIENT_DIR = (
    Path(__file__).resolve().parents[1] / "custom_components" / "infinitude_beyond"
)
sys.path.insert(0, str(CLIENT_DIR))

FIXTURES = Path(__file__).parent / "fixtures"

# Layer 2 (tests/ha/) requires Home Assistant. When it isn't installed (the
# HA-free Layer 1 environment), skip collecting that subtree entirely.
try:
    import homeassistant  # noqa: F401
except ImportError:
    collect_ignore_glob = ["ha/*"]


def load_fixture(name: str) -> dict:
    """Load a JSON fixture by filename."""
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def fixtures() -> dict:
    """The default happy-path payloads for the four Infinitude endpoints."""
    return {
        "status": load_fixture("status.json"),
        "config": load_fixture("config.json"),
        "energy": load_fixture("energy.json"),
        "profile": load_fixture("profile.json"),
    }


def _build_app(payloads: dict, posts: list) -> web.Application:
    """An aiohttp app mimicking the Infinitude REST endpoints."""

    async def status(_):
        return web.json_response(payloads["status"])

    async def config(_):
        return web.json_response(payloads["config"])

    async def energy(_):
        return web.json_response(payloads["energy"])

    async def profile(_):
        return web.json_response(payloads["profile"])

    async def record(request):
        posts.append({"path": request.path, "data": dict(await request.post())})

    async def post_config(request):
        await record(request)
        # Infinitude can return a non-JSON body (or an empty one) on a successful
        # POST. _post calls resp.json() on it unconditionally, which raises a
        # JSONDecodeError -- the root of issues #38/#39. (HA's orjson loader also
        # raises on an empty body; a non-JSON body reproduces it regardless of
        # which JSON loader is in use.)
        return web.Response(text="Success", content_type="text/plain")

    async def post_json(request):
        await record(request)
        return web.json_response({})

    app = web.Application()
    app.router.add_get("/api/status/", status)
    app.router.add_get("/api/config/", config)
    app.router.add_get("/energy.json", energy)
    app.router.add_get("/profile.json", profile)
    app.router.add_post("/api/config", post_config)
    app.router.add_post("/api/{zone}/activity/{activity}", post_json)
    app.router.add_post("/api/{zone}/hold", post_json)
    return app


async def _connect(payloads: dict):
    """Start a test server and a client connected to it.

    Returns (infinitude, server, posts). ``posts`` is a live list of recorded
    POST requests; the caller owns shutdown.
    """
    from infinitude.api import Infinitude

    posts: list = []
    server = TestServer(_build_app(payloads, posts))
    await server.start_server()
    inf = Infinitude("127.0.0.1", port=server.port)
    await inf.connect()
    inf.posts = posts  # type: ignore[attr-defined]
    return inf, server


@pytest_asyncio.fixture
async def infinitude(fixtures):
    """A connected client backed by happy-path fixtures over real HTTP.

    ``inf.posts`` records POST requests for assertions.
    """
    inf, server = await _connect(fixtures)
    yield inf
    await inf._session.close()
    await server.close()


# NOTE: there is intentionally no "no_schedule" connected fixture. connect()
# calls _update_activities() for every zone, which spins on a fully-disabled
# schedule (bug #42). Tests cover that case by swapping config AFTER connect.
