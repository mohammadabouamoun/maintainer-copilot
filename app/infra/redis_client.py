import structlog
import redis.asyncio as aioredis
from typing import Optional

logger = structlog.get_logger()

_redis_client: Optional[aioredis.Redis] = None


def get_redis_client() -> aioredis.Redis:
    """
    Returns the shared Redis async client singleton.
    Must be initialized via init_redis_client() during lifespan startup.
    """
    if _redis_client is None:
        raise RuntimeError("Redis client has not been initialized. Call init_redis_client() first.")
    return _redis_client


async def init_redis_client(redis_url: str) -> aioredis.Redis:
    """
    Creates and stores a singleton Redis async client, verifying connectivity via PING.
    Called once during FastAPI lifespan startup (refuse-to-boot pattern).
    """
    global _redis_client
    client = aioredis.from_url(
        redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    # Refuse-to-boot: verify Redis is reachable
    await client.ping()
    _redis_client = client
    logger.info("Redis client initialized and connected", url=redis_url)
    return _redis_client


async def close_redis_client() -> None:
    """Gracefully closes the Redis connection pool on application shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis client closed.")
