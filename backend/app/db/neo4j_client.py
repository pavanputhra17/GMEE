from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import get_settings


class Neo4jClient:
    def __init__(self) -> None:
        self.driver: AsyncDriver | None = None

    async def get_driver(self) -> AsyncDriver:
        if self.driver is None:
            settings = get_settings()
            self.driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
            )
        return self.driver
    
    async def close(self) -> None:
        if self.driver is not None:
            await self.driver.close()

neo4j_client = Neo4jClient()
