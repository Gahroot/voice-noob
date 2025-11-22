"""Redis connection management."""

from typing import TYPE_CHECKING

import redis.asyncio as aioredis

from app.core.config import settings

if TYPE_CHECKING:
    from redis.asyncio import Redis
else:
    Redis = object  # type: ignore[misc,assignment]

redis_client: "Redis | None" = None


async def get_redis() -> "Redis":
    """Get Redis client instance."""
    global redis_client
    if redis_client is None:
        redis_client = await aioredis.from_url(
            str(settings.REDIS_URL),
            encoding="utf-8",
            decode_responses=True,
        )
    return redis_client


async def close_redis() -> None:
    """Close Redis connection."""
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None
