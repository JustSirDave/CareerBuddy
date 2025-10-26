import os, time
from redis import Redis

_redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))

def seen_or_mark(msg_id: str, ttl_sec: int = 300) -> bool:
    """
    Returns True if we've already processed msg_id.
    Otherwise sets a short TTL key and returns False.
    """
    if not msg_id:
        return False
    # SETNX msg:<id> 1 EX 300
    key = f"msg:{msg_id}"
    was_set = _redis.set(name=key, value="1", ex=ttl_sec, nx=True)
    return not bool(was_set)  # True => already seen
