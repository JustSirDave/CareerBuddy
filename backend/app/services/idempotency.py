# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Xenaptis Technologies
"""
CareerBuddy - Idempotency Service
Simple Redis-based idempotency checker for webhook deduplication.
Author: Sir Dave
"""
import redis.asyncio as aioredis
from loguru import logger

from app.config import settings

r = aioredis.from_url(settings.redis_url, decode_responses=True)


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
