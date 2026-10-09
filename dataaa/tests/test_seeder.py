"""Seeder coverage: seeds an empty DB once, then no-ops (idempotent)."""
import logging
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source import Source
from app.services import seeder


class _FakeSessionMaker:
    """Stand-in for async_session_maker yielding the fixture session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def __call__(self) -> AbstractAsyncContextManager[AsyncSession]:
        return self._cm()

    @asynccontextmanager
    async def _cm(self) -> AsyncIterator[AsyncSession]:
        yield self._session


async def test_seed_sources_populates_empty_db(db_session, monkeypatch, caplog):
    monkeypatch.setattr(seeder, "async_session_maker", _FakeSessionMaker(db_session))
    with caplog.at_level(logging.INFO, logger="app.services.seeder"):
        await seeder.seed_sources()

    assert "Initial sources seeded successfully" in caplog.text
    sources = (await db_session.execute(select(Source))).scalars().all()
    assert len(sources) == 3  # BBC World, NewsAPI, Reddit r/science


async def test_seed_sources_is_idempotent(db_session, monkeypatch):
    monkeypatch.setattr(seeder, "async_session_maker", _FakeSessionMaker(db_session))
    await seeder.seed_sources()
    await seeder.seed_sources()  # second run finds existing sources → no dupes

    sources = (await db_session.execute(select(Source))).scalars().all()
    assert len(sources) == 3
