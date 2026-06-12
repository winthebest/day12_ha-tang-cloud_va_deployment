"""
Production API — bọc Day09 ShoppingAssistant (LangGraph multi-agent).
"""
import asyncio
import json
import logging
import os
import signal
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.api_config import api_settings
from app.auth import verify_api_key
from app.cost_guard import check_budget, estimate_cost
from app.graph import ShoppingAssistant
from app.rate_limiter import check_rate_limit
from app.redis_store import append_history, get_history, ping

logging.basicConfig(
    level=getattr(logging, api_settings.log_level.upper(), logging.INFO),
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_in_flight_requests = 0
_request_count = 0
INSTANCE_ID = os.getenv("INSTANCE_ID", f"instance-{os.getpid()}")
_assistant: ShoppingAssistant | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready, _assistant
    logger.info(json.dumps({
        "event": "startup",
        "app": api_settings.app_name,
        "version": api_settings.app_version,
        "environment": api_settings.environment,
        "instance_id": INSTANCE_ID,
    }))
    if not ping():
        raise RuntimeError("Redis is required but not reachable. Check REDIS_URL.")
    _assistant = ShoppingAssistant()
    _is_ready = True
    logger.info(json.dumps({"event": "ready", "instance_id": INSTANCE_ID}))

    yield

    _is_ready = False
    timeout = 30
    elapsed = 0
    while _in_flight_requests > 0 and elapsed < timeout:
        logger.info(json.dumps({"event": "shutdown_wait", "in_flight": _in_flight_requests}))
        time.sleep(1)
        elapsed += 1
    logger.info(json.dumps({"event": "shutdown_complete", "instance_id": INSTANCE_ID}))


app = FastAPI(
    title=api_settings.app_name,
    version=api_settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if api_settings.environment != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=api_settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _in_flight_requests
    start = time.time()
    _request_count += 1
    _in_flight_requests += 1
    try:
        response: Response = await call_next(request)
        duration = round((time.time() - start) * 1000, 1)
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration,
            "instance_id": INSTANCE_ID,
        }))
        return response
    finally:
        _in_flight_requests -= 1


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str = Field(..., min_length=1, max_length=128)


class AskResponse(BaseModel):
    question: str
    answer: str
    user_id: str
    turn: int
    history_count: int
    served_by: str
    timestamp: str


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(body: AskRequest, _key: str = Depends(verify_api_key)):
    if _assistant is None:
        raise HTTPException(status_code=503, detail="Agent not ready")

    check_rate_limit(body.user_id)

    input_tokens = len(body.question.split()) * 2
    check_budget(body.user_id, estimate_cost(input_tokens, 0))

    logger.info(json.dumps({
        "event": "agent_call",
        "user_id": body.user_id,
        "q_len": len(body.question),
        "instance_id": INSTANCE_ID,
    }))

    result = await asyncio.to_thread(_assistant.ask, body.question)
    answer = result.get("final_answer") or "(no answer)"

    output_tokens = len(answer.split()) * 2
    check_budget(body.user_id, estimate_cost(0, output_tokens))

    append_history(body.user_id, "user", body.question)
    append_history(body.user_id, "assistant", answer)
    updated = get_history(body.user_id)
    user_turns = sum(1 for m in updated if m["role"] == "user")

    return AskResponse(
        question=body.question,
        answer=answer,
        user_id=body.user_id,
        turn=user_turns,
        history_count=len(updated),
        served_by=INSTANCE_ID,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/health", tags=["Operations"])
def health():
    redis_ok = ping()
    return {
        "status": "ok" if redis_ok else "degraded",
        "version": api_settings.app_version,
        "redis_connected": redis_ok,
        "instance_id": INSTANCE_ID,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    if not _is_ready:
        raise HTTPException(status_code=503, detail="Agent not ready")
    if not ping():
        raise HTTPException(status_code=503, detail="Redis not available")
    return {"ready": True, "instance_id": INSTANCE_ID}


def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum, "instance_id": INSTANCE_ID}))


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=api_settings.host,
        port=api_settings.port,
        reload=api_settings.debug,
        timeout_graceful_shutdown=30,
    )
