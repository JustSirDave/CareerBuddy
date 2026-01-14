"""
CareerBuddy - Idempotency Service
Simple Redis-based idempotency checker for webhook deduplication.
Author: Sir Dave
"""
import redis
import os
from loguru import logger

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

try:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    r.ping()  # Test connection
    logger.info(f"[idempotency] Connected to Redis at {REDIS_URL}")
except Exception as e:
    logger.error(f"[idempotency] Failed to connect to Redis: {e}")
    r = None


def seen_or_mark(key: str, ttl: int = 3600) -> bool:
    """
        Check if a key has been seen before. If not, mark it.

        Args:
            key: Unique identifier (e.g., Telegram message ID)
            ttl: Time-to-live in seconds (default: 1 hour)

        Returns:
            True if key was already seen, False if this is the first time
    """
    if r is None:
        logger.warning("[idempotency] Redis not available, skipping deduplication")
        return False

    try:
        # Check if key exists
        if r.exists(key):
            logger.debug(f"[idempotency] Key '{key}' already seen")
            return True

        # Mark as seen
        r.setex(key, ttl, "1")
        logger.debug(f"[idempotency] Marked key '{key}' as seen (TTL: {ttl}s)")
        return False

    except Exception as e:
        logger.error(f"[idempotency] Error checking key '{key}': {e}")
        return False  # Fail open to avoid blocking valid requests