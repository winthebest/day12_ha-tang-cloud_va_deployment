"""Redis sliding-window rate limiter — 10 requests/minute per user."""
import time

from fastapi import HTTPException

from app.config import settings
from app.redis_store import get_redis


def check_rate_limit(user_id: str) -> None:
    """Raise 429 if user exceeds rate limit within the 60-second window."""
    now = time.time()
    window_start = now - 60
    key = f"ratelimit:{user_id}"

    r = get_redis()
    r.zremrangebyscore(key, 0, window_start)
    count = r.zcard(key)

    if count >= settings.rate_limit_per_minute:
        oldest = r.zrange(key, 0, 0, withscores=True)
        retry_after = 60
        if oldest:
            retry_after = max(1, int(oldest[0][1] + 60 - now))
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "limit": settings.rate_limit_per_minute,
                "window_seconds": 60,
                "retry_after_seconds": retry_after,
            },
            headers={
                "X-RateLimit-Limit": str(settings.rate_limit_per_minute),
                "X-RateLimit-Remaining": "0",
                "Retry-After": str(retry_after),
            },
        )

    r.zadd(key, {f"{now:.6f}": now})
    r.expire(key, 61)
