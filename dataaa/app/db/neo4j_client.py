from __future__ import annotations

import logging

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class Neo4jClient:
    def __init__(self) -> None:
        self.driver: AsyncDriver | None = None
        self._disabled = False

    async def get_driver(self) -> AsyncDriver:
        if self._disabled:
            raise RuntimeError("Neo4j is not configured (NEO4J_URI is empty)")
        if self.driver is None:
            settings = get_settings()
            if not settings.NEO4J_URI:
                self._disabled = True
                logger.warning("NEO4J_URI not set — Neo4j features disabled")
                raise RuntimeError("Neo4j is not configured (NEO4J_URI is empty)")
            self.driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
            )
        return self.driver
    
    async def close(self) -> None:
        if self.driver is not None:
            await self.driver.close()

neo4j_client = Neo4jClient()

