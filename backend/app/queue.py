"""Redis-backed job queue."""

import uuid

import redis.asyncio as aioredis

from backend.app.config import REDIS_HOST, REDIS_PORT

QUEUE_KEY = "sa:jobs:pending"

_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = aioredis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, decode_responses=True
        )
    return _pool


async def enqueue_job(job_id: uuid.UUID) -> None:
    r = await get_redis()
    await r.lpush(QUEUE_KEY, str(job_id))


async def dequeue_job(timeout: int = 5) -> uuid.UUID | None:
    """Block-pop a job_id from the queue. Returns None on timeout."""
    r = await get_redis()
    result = await r.brpop(QUEUE_KEY, timeout=timeout)
    if result is None:
        return None
    _, raw_id = result
    return uuid.UUID(raw_id)


async def close_redis() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
