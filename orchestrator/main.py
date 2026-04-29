"""
INA Orchestrator — Main API Gateway and Workflow Engine

This module serves as the central orchestrator for the bargaining chatbot.
It handles:
1. Security: Validating tenant API session tokens against Redis.
2. Rate Limiting: Applying connection limits to prevent abuse.
3. Execution: Orchestrating the flow of conversation through the LangGraph workflow.
4. Persistence: Handling final state sync to the central database.
"""

import os
import logging
import uuid
from contextlib import asynccontextmanager

from datetime import datetime, timezone
import httpx

from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

try:
    from prometheus_fastapi_instrumentator import Instrumentator

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from orchestrator.lib import state_manager
from orchestrator.lib.http_pool import close_http_client
from orchestrator.graph.workflow import build_workflow
from orchestrator.session_schemas import SessionData

# ---------------------- Logging ----------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("orchestrator")

# 🔥 Build Graph Once (Startup Time)
graph_app = build_workflow()


# ---------------------- Rate Limiter ----------------------
def _get_session_id_from_request(request: Request) -> str:
    """
    Extract session_id from the request body for rate limiting.
    Falls back to client IP if session_id can't be extracted.
    This ensures rate limiting is per-session, not just per-IP.
    """
    # For non-JSON requests or health checks, use IP
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_get_session_id_from_request)


# ---------------------- Lifespan ----------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    logger.info("INA Orchestrator starting up...")
    yield
    logger.info("INA Orchestrator shutting down...")
    await close_http_client()
    await state_manager.close_redis()


# ---------------------- App Init ----------------------
app = FastAPI(title="INA Orchestrator", lifespan=lifespan)

# Prometheus Instrumentation
if PROMETHEUS_AVAILABLE:
    Instrumentator().instrument(app).expose(app)

# Attach limiter to app state (required by slowapi)
app.state.limiter = limiter


# ---------------------- Rate Limit Error Handler ----------------------
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Return a clean JSON 429 response when rate limit is exceeded."""
    logger.warning(
        "Rate limit exceeded — client=%s path=%s",
        request.client.host if request.client else "unknown",
        request.url.path,
    )
    return JSONResponse(
        status_code=429,
        content={
            "error": True,
            "code": "RATE_LIMITED",
            "message": "Too many requests. Please slow down.",
            "retry_after": str(exc.detail),
        },
    )


from starlette.exceptions import HTTPException as StarletteHTTPException


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": True, "code": "HTTP_ERROR", "message": str(exc.detail)},
    )


# ---------------------- CORS ----------------------
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = (
    ["*"]
    if _raw_origins.strip() == "*"
    else [o.strip() for o in _raw_origins.split(",") if o.strip()]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------- Request ID Middleware ----------------------
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Generate a unique X-Request-ID for every request and attach to logs + response."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    # Store on request state so nodes/clients can access it
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ---------------------- Schemas ----------------------
class ChatInput(BaseModel):
    user_id: str
    message: str


class ChatOutput(BaseModel):
    response: str
    is_fallback: bool = False
    deal_accepted: bool = False
    negotiation_status: str = (
        "in_progress"  # "in_progress" | "deal_accepted" | "locked"
    )
    final_price: float | None = None
    offer_count: int = 0
    is_locked: bool = False


# =====================================================
# 🔐 AUTH DEPENDENCY — Session Validation
# =====================================================
async def validate_session(payload: ChatInput) -> SessionData:
    """
    FastAPI dependency that validates the session from Redis.

    Auth logic:
        1. Session ID se Redis mein session fetch karo.
        2. Agar session nahi mili → 401 Unauthorized (invalid/expired).
        3. Agar session structure corrupt hai → 401 Unauthorized (invalid data).
        4. Valid session return karo as a Pydantic SessionData object.
    """
    redis_key = payload.user_id

    # 1. Fetch session from Redis
    raw_session = await state_manager.get_session(redis_key)

    if raw_session is None:
        logger.warning("Auth failed: session not found — user_id=%s", payload.user_id)
        raise HTTPException(
            status_code=401,
            detail={
                "error": True,
                "code": "SESSION_EXPIRED",
                "message": "Unauthorized: Invalid or expired session ID.",
            },
        )

    # 2. Validate session structure
    try:
        session = SessionData(**raw_session)
    except ValidationError as e:
        logger.warning(
            "Auth failed: corrupt session data — user_id=%s errors=%s",
            payload.user_id,
            e.errors(),
        )
        raise HTTPException(
            status_code=401,
            detail={
                "error": True,
                "code": "SESSION_CORRUPT",
                "message": "Unauthorized: Session data is invalid or incomplete.",
            },
        )

    return session


# ---------------------- Health (no rate limit) ----------------------
@app.api_route("/", methods=["GET", "HEAD"])
async def home():
    return {"message": "Orchestrator is running!"}


@app.get("/ping-redis")
async def ping_redis():
    ok = await state_manager.ping_redis()
    if not ok:
        raise HTTPException(
            status_code=503,
            detail={
                "error": True,
                "code": "REDIS_UNAVAILABLE",
                "message": "Redis not reachable",
            },
        )

    test_sid = "ping-test-session"
    success = await state_manager.set_session(test_sid, {"hello": "redis"})
    data = await state_manager.get_session(test_sid)

    return {"redis_ping": ok, "write_ok": success, "read_data": data}


@app.get("/health")
async def health_check():
    redis_ok = await state_manager.ping_redis()
    return {"status": "ok" if redis_ok else "degraded"}


# ---------------------- DB Sync Task ----------------------
async def send_negotiation_outcome_to_db(
    session_id: str,
    outcome: str,
    asking_price: float,
    final_price: float,
    language: str,
    history: list,
):
    """Fire-and-forget task to send negotiation summary to external DB."""
    try:
        user_turns = sum(1 for msg in history if msg.get("from") == "user")
        discount_percent = 0.0
        if asking_price > 0 and final_price:
            discount_percent = round(
                ((asking_price - final_price) / asking_price) * 100, 2
            )

        payload = {
            "session_id": session_id,
            "outcome": outcome,
            "asking_price": asking_price,
            "final_price": final_price,
            "discount_percent": discount_percent,
            "total_turns": user_turns,
            "user_language": language,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "message_history": history,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://ina-backend-fyp.onrender.com/api/negotiations/", json=payload
            )
            resp.raise_for_status()
            logger.info(
                "Successfully sent negotiation outcome to DB for session %s", session_id
            )

    except httpx.HTTPStatusError as e:
        logger.error(
            "DB Sync HTTP Error [%s]: %s - Response: %s", session_id, e, e.response.text
        )
    except Exception as e:
        logger.error(
            "Failed to send negotiation outcome to DB for session %s. Exception type: %s, Error: %s",
            session_id,
            type(e).__name__,
            str(e),
            exc_info=True,
        )


# =====================================================
# 🔥 MAIN CHAT ENDPOINT (Session-Authenticated + Rate-Limited)
# =====================================================
@app.post("/ina/v1/chat", response_model=ChatOutput)
@limiter.limit("10/minute")
async def chat_endpoint(
    request: Request,
    payload: ChatInput,
    background_tasks: BackgroundTasks,
    _validated_session: SessionData = Depends(validate_session),
):
    """
    Main chat endpoint.
    - Auth: handled by validate_session dependency
    - Rate limit: 10 requests per minute per client IP (application layer)
    - Nginx also enforces 10 req/s per IP (gateway layer)
    """

    try:
        redis_key = payload.user_id

        # ------------------------------------------------
        # ------------------------------------------------
        # 🔒 Acquire distributed lock (Race Condition Fix)
        # Ensures only one request processes a session at a time.
        # ------------------------------------------------
        async with state_manager.session_lock(redis_key):
            # Re-read inside lock so we always work on the latest state.
            latest_raw = await state_manager.get_session(redis_key)
            if latest_raw is None:
                raise HTTPException(
                    status_code=401,
                    detail={
                        "error": True,
                        "code": "SESSION_EXPIRED",
                        "message": "Unauthorized: Invalid or expired session ID.",
                    },
                )

            latest_session = SessionData(**latest_raw)
            mam = latest_session.mam
            asking_price = latest_session.asking_price
            offer_count = latest_session.offer_count
            current_status = latest_session.status
            last_bot_offer = latest_session.last_bot_offer

            # ------------------------------------------------
            # 🚫 OFFER LIMIT CHECK — Reject if session is locked
            # After 5 valid offers, no further bargaining allowed.
            # ------------------------------------------------
            if current_status == "locked":
                logger.info(
                    "Session %s is locked (offer_count=%s). Returning last bot offer.",
                    redis_key,
                    offer_count,
                )
                return ChatOutput(
                    response=f"This negotiation session has been finalized. The locked price is {last_bot_offer}.",
                    is_fallback=False,
                    deal_accepted=True,
                    negotiation_status="locked",
                    final_price=last_bot_offer,
                    offer_count=offer_count,
                    is_locked=True,
                )

            history = list(latest_session.messages)
            history.append(
                {
                    "from": "user",
                    "text": payload.message,
                }
            )

            # --------------------------------------------
            # LangGraph Execution
            # --------------------------------------------
            result = None
            try:
                state = {
                    "session_id": redis_key,
                    "mam": mam,
                    "asking_price": asking_price,
                    "user_input": payload.message,
                    "history": history,
                    "request_id": getattr(request.state, "request_id", ""),
                }

                result = await graph_app.ainvoke(state)

                ai_response = result.get(
                    "final_response",
                    "Let me think about that for a moment.",
                )
                brain_action = result.get("brain_action")
                brain_key = result.get("response_key")
                is_fallback = result.get("is_fallback", False)

            except Exception:
                logger.exception("Graph failed, using safe fallback")
                ai_response = (
                    "Let me think about that for a moment. Could you please try again?"
                )
                brain_action = "FALLBACK"
                brain_key = "GRAPH_FAIL"
                is_fallback = True

            # --------------------------------------------
            # Save updated history back to Redis
            # --------------------------------------------

            # Retroactively add user_offer to the last user message now that NLU has parsed it
            user_offer = result.get("user_offer") if result else None
            user_intent = result.get("intent") if result else None
            # Update the last element (which is the user message we just appended)
            if history and history[-1].get("from") == "user":
                history[-1]["user_offer"] = user_offer

            # ------------------------------------------------
            # 📊 Increment offer_count on valid monetary offers
            # ------------------------------------------------
            new_offer_count = offer_count
            new_status = current_status
            new_last_bot_offer = last_bot_offer

            if user_intent == "MAKE_OFFER" and user_offer:
                new_offer_count = offer_count + 1
                logger.info(
                    "[Session %s] Offer #%s received (offer=%s)",
                    redis_key,
                    new_offer_count,
                    user_offer,
                )

            # Update last_bot_offer from this turn's counter price
            counter_price = result.get("counter_price") if result else None
            if counter_price:
                new_last_bot_offer = float(counter_price)

            # Lock session after 5th offer
            if new_offer_count >= 5 and new_status == "negotiating":
                new_status = "locked"
                logger.info(
                    "[Session %s] 5-offer limit reached. Locking session. Final price: %s",
                    redis_key,
                    new_last_bot_offer,
                )

            history.append(
                {
                    "from": "ina",
                    "text": ai_response,
                    "brain_action": brain_action,
                    "brain_key": brain_key,
                    "bot_offer": counter_price,
                }
            )

            updated_session = latest_session.model_dump()
            updated_session["messages"] = history
            updated_session["offer_count"] = new_offer_count
            updated_session["status"] = new_status
            updated_session["last_bot_offer"] = new_last_bot_offer
            await state_manager.set_session(redis_key, updated_session)

            # Fire off DB save if deal was naturally closed OR session just got locked
            if brain_action in ("ACCEPT", "DEAL") or new_status == "locked":
                db_final_price = new_last_bot_offer or user_offer or 0.0
                language = result.get("language", "english") if result else "english"
                db_outcome = (
                    "ACCEPTED" if brain_action in ("ACCEPT", "DEAL") else "FORCED_DEAL"
                )
                background_tasks.add_task(
                    send_negotiation_outcome_to_db,
                    session_id=redis_key,
                    outcome=db_outcome,
                    asking_price=asking_price,
                    final_price=float(db_final_price),
                    language=language,
                    history=history,
                )

        deal_accepted = brain_action in ("ACCEPT", "DEAL") or new_status == "locked"
        negotiation_status = (
            "locked"
            if new_status == "locked"
            else ("deal_accepted" if deal_accepted else "in_progress")
        )
        out_final_price = float(new_last_bot_offer or 0.0) if deal_accepted else None
        return ChatOutput(
            response=ai_response,
            is_fallback=is_fallback,
            deal_accepted=deal_accepted,
            negotiation_status=negotiation_status,
            final_price=out_final_price,
            offer_count=new_offer_count,
            is_locked=(new_status == "locked"),
        )

    except HTTPException:
        raise

    except TimeoutError:
        logger.warning("Session lock timeout for user_id=%s", payload.user_id)
        raise HTTPException(
            status_code=409,
            detail={
                "error": True,
                "code": "SESSION_LOCKED",
                "message": "Another request is already processing this session. Please retry.",
            },
        )

    except Exception as e:
        logger.exception("Unexpected error for session %s: %s", payload.user_id, e)
        raise HTTPException(
            status_code=500,
            detail={
                "error": True,
                "code": "INTERNAL_ERROR",
                "message": "Internal server error",
            },
        )
