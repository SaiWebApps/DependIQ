"""Neo4j async connection management."""

import logging

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.config import Config

logger = logging.getLogger(__name__)

_driver: AsyncDriver | None = None


async def get_neo4j_driver() -> AsyncDriver:
    """Get or create the Neo4j async driver."""
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            Config.NEO4J_URI,
            auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD),
        )
        logger.info("Neo4j driver created for %s", Config.NEO4J_URI)
    return _driver


async def close_neo4j() -> None:
    """Close the Neo4j driver on shutdown."""
    global _driver
    if _driver:
        await _driver.close()
        _driver = None
        logger.info("Neo4j driver closed")


async def neo4j_health_check() -> dict:
    """Check Neo4j connectivity. Returns status dict."""
    try:
        driver = await get_neo4j_driver()
        async with driver.session() as session:
            result = await session.run("RETURN 1 AS n")
            record = await result.single()
            if record and record["n"] == 1:
                return {"status": "connected"}
        return {"status": "error", "detail": "unexpected result"}
    except Exception as e:
        logger.warning("Neo4j health check failed: %s", e)
        return {"status": "disconnected", "detail": str(e)}
