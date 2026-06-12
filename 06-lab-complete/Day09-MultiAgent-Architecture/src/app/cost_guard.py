"""Monthly cost guard tracked in Redis."""
from datetime import datetime

from fastapi import HTTPException

from app.api_config import api_settings
from app.redis_store import get_redis

PRICE_PER_1K_INPUT = 0.00015
PRICE_PER_1K_OUTPUT = 0.0006


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        (input_tokens / 1000) * PRICE_PER_1K_INPUT
        + (output_tokens / 1000) * PRICE_PER_1K_OUTPUT
    )


def check_budget(user_id: str, estimated_cost: float) -> None:
    month_key = datetime.now().strftime("%Y-%m")
    key = f"budget:{user_id}:{month_key}"

    r = get_redis()
    current = float(r.get(key) or 0)
    if current + estimated_cost > api_settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Monthly budget exceeded",
                "used_usd": round(current, 6),
                "budget_usd": api_settings.monthly_budget_usd,
            },
        )

    r.incrbyfloat(key, estimated_cost)
    r.expire(key, 32 * 24 * 3600)
