"""
CareerBuddy - Idempotency Service
Simple Redis-based idempotency checker for webhook deduplication.
Author: Sir Dave
"""
import redis.asyncio as aioredis
import os
from loguru import logger

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

r = aioredis.from_url(REDIS_URL, decode_responses=True)


async def seen_or_mark(key: str, ttl: int = 3600) -> bool:
    """
        Check if a key has been seen before. If not, mark it.

        Args:
            key: Unique identifier (e.g., Telegram message ID)
            ttl: Time-to-live in seconds (default: 1 hour)

        Returns:
            True if key was already seen, False if this is the first time
    """
    try:
        result = await r.set(key, "1", nx=True, ex=ttl)
        if result is None:
            logger.debug(f"[idempotency] Key '{key}' already seen")
            return True
        logger.debug(f"[idempotency] Marked key '{key}' as seen (TTL: {ttl}s)")
        return False

    except Exception as e:
        logger.error(f"[idempotency] Error checking key '{key}': {e}")
        return False  # Fail open to avoid blocking valid requests
