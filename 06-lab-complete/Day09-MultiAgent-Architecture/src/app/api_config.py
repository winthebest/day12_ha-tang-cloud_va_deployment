"""Production API config — tách khỏi app.config (agent Day09)."""
import logging
import os
from dataclasses import dataclass, field


@dataclass
class ApiSettings:
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "Day09 Multi-Agent API"))
    app_version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "1.0.0"))

    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", "dev-key-change-me"))
    allowed_origins: list = field(
        default_factory=lambda: os.getenv("ALLOWED_ORIGINS", "*").split(",")
    )

    rate_limit_per_minute: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
    )
    monthly_budget_usd: float = field(
        default_factory=lambda: float(os.getenv("MONTHLY_BUDGET_USD", "10.0"))
    )

    redis_url: str = field(default_factory=lambda: _resolve_redis_url())

    def validate(self):
        logger = logging.getLogger(__name__)
        if self.environment == "production" and self.agent_api_key == "dev-key-change-me":
            raise ValueError("AGENT_API_KEY must be set in production!")
        if self.environment == "production" and not _is_valid_redis_url(self.redis_url):
            raise ValueError("REDIS_URL is missing or invalid in production!")
        if not os.getenv("GOOGLE_API_KEY") and not os.getenv("OPENAI_API_KEY"):
            logger.warning("No LLM API key set — agent may fail on /ask")
        return self


def _resolve_redis_url() -> str:
    for key in ("REDIS_PRIVATE_URL", "REDIS_URL", "REDISURL"):
        value = os.getenv(key, "").strip()
        if value:
            return value
    return "redis://localhost:6379/0"


def _is_valid_redis_url(url: str) -> bool:
    if not url or url == "redis://localhost:6379/0":
        return False
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.scheme in ("redis", "rediss") and bool(parsed.hostname)
    except Exception:
        return False


api_settings = ApiSettings().validate()
