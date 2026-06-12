"""Monthly cost guard — $10/user/month tracked in Redis."""
from datetime import datetime

from fastapi import HTTPException

from app.config import settings
from app.redis_store import get_redis

PRICE_PER_1K_INPUT_TOKENS = 0.00015
PRICE_PER_1K_OUTPUT_TOKENS = 0.0006


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        (input_tokens / 1000) * PRICE_PER_1K_INPUT_TOKENS
        + (output_tokens / 1000) * PRICE_PER_1K_OUTPUT_TOKENS
    )


def check_budget(user_id: str, estimated_cost: float) -> None:
    """Raise 402 if monthly budget would be exceeded."""
    month_key = datetime.now().strftime("%Y-%m")
    key = f"budget:{user_id}:{month_key}"

    r = get_redis()
    current = float(r.get(key) or 0)
    if current + estimated_cost > settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Monthly budget exceeded",
                "used_usd": round(current, 6),
                "budget_usd": settings.monthly_budget_usd,
                "resets_at": "first day of next month",
            },
        )

    r.incrbyfloat(key, estimated_cost)
    r.expire(key, 32 * 24 * 3600)


def get_spending(user_id: str) -> float:
    month_key = datetime.now().strftime("%Y-%m")
    key = f"budget:{user_id}:{month_key}"
    return float(get_redis().get(key) or 0)
