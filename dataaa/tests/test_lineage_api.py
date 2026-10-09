"""Claim-lineage inspector: sanitisation, degenerate inputs and the diff loop.

The version chain is paired with `itertools.pairwise`; the import regression
test below exists because a missing import made every lineage request raise
NameError (latent 500) while the unit suite stayed green. The DB-backed BFS is
Postgres-specific (`id::text`, UUID casts) and is exercised live in dev; the
paths tested here never reach the database, so they run on SQLite.
"""

import itertools

import pytest

from app.api.v1 import lineage as lineage_api


def test_pairwise_is_imported():
    # regression: the diff comprehension calls pairwise() on every request
    assert lineage_api.pairwise is itertools.pairwise


def test_clean_strips_html_and_collapses_whitespace():
    assert lineage_api._clean("<p>Hello <b>world</b></p>", 100) == "Hello world"
    assert lineage_api._clean("  a\n\n   b  ", 100) == "a b"
    assert lineage_api._clean("Tom &amp; Jerry", 100) == "Tom & Jerry"


def test_clean_drops_empty_and_truncates():
    assert lineage_api._clean(None, 100) is None
    assert lineage_api._clean("   ", 100) is None
    assert lineage_api._clean("abcdef", 3) == "abc"


def test_chain_caps_are_ordered():
    # the rendered chain must fit inside the inspected component
    assert 1 < lineage_api.MAX_VERSIONS <= lineage_api.MAX_COMPONENT
    assert lineage_api.MAX_HOPS >= 1


@pytest.mark.asyncio
async def test_lineage_rejects_non_uuid(async_client):
    # the UUID guard runs before any DB access, so this runs on SQLite
    resp = await async_client.get("/api/v1/graph/lineage/not-a-uuid")
    assert resp.status_code == 400


def test_lineage_and_simulate_routes_are_mounted():
    """Asserted through the OpenAPI schema: FastAPI >= 0.14x / Starlette 1.x
    nests included routers instead of flattening them into `app.routes`."""
    from app.main import app

    paths = set(app.openapi()["paths"])
    assert "/api/v1/graph/lineage/{claim_id}" in paths
    assert "/api/v1/graph/simulate" in paths
