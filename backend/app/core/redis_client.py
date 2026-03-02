"""
Singleton Redis async client — dùng chung toàn bộ app.

Usage:
    from app.core.redis_client import get_redis
    redis = await get_redis()
    await redis.set("key", "value", ex=300)
    val = await redis.get("key")
"""
import redis.asyncio as aioredis
from app.config import settings

_redis_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def close_redis():
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
