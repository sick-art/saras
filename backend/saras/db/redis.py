import redis.asyncio as aioredis

from saras.config import get_settings

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        settings = get_settings()
        _client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def publish(channel: str, message: str) -> None:
    await get_redis().publish(channel, message)


async def close() -> None:
    global _client
    if _client:
        await _client.aclose()
        _client = None
