"""Redis-backed state — conversation history, shared across instances."""
import json
import logging
from datetime import datetime, timezone

import redis

from app.config import settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def ping() -> bool:
    if not settings.redis_url:
        logger.error(json.dumps({"event": "redis_ping_failed", "error": "REDIS_URL is empty"}))
        return False
    try:
        get_redis().ping()
        return True
    except Exception as exc:
        logger.error(json.dumps({
            "event": "redis_ping_failed",
            "error": str(exc),
            "redis_url_set": bool(settings.redis_url),
        }))
        return False


def get_history(user_id: str) -> list[dict]:
    entries = get_redis().lrange(f"history:{user_id}", 0, -1)
    return [json.loads(entry) for entry in entries]


def append_history(user_id: str, role: str, content: str) -> None:
    entry = json.dumps({
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    key = f"history:{user_id}"
    r = get_redis()
    r.rpush(key, entry)
    r.ltrim(key, -20, -1)
    r.expire(key, 30 * 24 * 3600)
