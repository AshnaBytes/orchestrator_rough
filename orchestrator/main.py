"""
INA Orchestrator — Main Application

Auth Model:
    The monolith backend validates tenant API keys and creates sessions
    in Redis. The session_id returned to the tenant frontend acts as the
    auth token. On every /chat request, the orchestrator validates this
    session_id exists in Redis and has the correct structure.

    Flow: Tenant → Monolith (API key) → Redis session → Orchestrator (session_id)

Rate Limiting:
    Two layers of protection:
    1. Nginx (API gateway) — IP-based rate limiting (10 req/s per IP)
    2. SlowAPI (application) — session-based rate limiting (10 req/min per session)
"""

import os
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from prometheus_fastapi_instrumentator import Instrumentator

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from orchestrator.lib import state_manager
from orchestrator.lib.state_manager import session_lock
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

from fastapi.exceptions import RequestValidationError
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
    ["*"] if _raw_origins.strip() == "*"
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
        logger.warning(
            "Auth failed: session not found — user_id=%s", payload.user_id
        )
        raise HTTPException(
            status_code=401,
            detail={"error": True, "code": "SESSION_EXPIRED", "message": "Unauthorized: Invalid or expired session ID."},
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
            detail={"error": True, "code": "SESSION_CORRUPT", "message": "Unauthorized: Session data is invalid or incomplete."},
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
        raise HTTPException(status_code=503, detail={"error": True, "code": "REDIS_UNAVAILABLE", "message": "Redis not reachable"})

    test_sid = "ping-test-session"
    success = await state_manager.set_session(test_sid, {"hello": "redis"})
    data = await state_manager.get_session(test_sid)

    return {"redis_ping": ok, "write_ok": success, "read_data": data}


@app.get("/health")
async def health_check():
    redis_ok = await state_manager.ping_redis()
    return {"status": "ok" if redis_ok else "degraded"}


# =====================================================
# 🔥 MAIN CHAT ENDPOINT (Session-Authenticated + Rate-Limited)
# =====================================================
@app.post("/ina/v1/chat", response_model=ChatOutput)
@limiter.limit("10/minute")
async def chat_endpoint(
    request: Request,
    payload: ChatInput,
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
                    detail={"error": True, "code": "SESSION_EXPIRED", "message": "Unauthorized: Invalid or expired session ID."},
                )

            latest_session = SessionData(**latest_raw)
            mam = latest_session.mam
            asking_price = latest_session.asking_price

            history = list(latest_session.messages)
            history.append({
                "from": "user",
                "text": payload.message,
            })

            # --------------------------------------------
            # LangGraph Execution
            # --------------------------------------------
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
                    "Let me think about that for a moment. "
                    "Could you please try again?"
                )
                brain_action = "FALLBACK"
                brain_key = "GRAPH_FAIL"
                is_fallback = True

            # --------------------------------------------
            # Save updated history back to Redis
            # --------------------------------------------
            
            # Retroactively add user_offer to the last user message now that NLU has parsed it
            user_offer = result.get("user_offer") if result else None
            # Update the last element (which is the user message we just appended)
            if history and history[-1].get("from") == "user":
                history[-1]["user_offer"] = user_offer

            history.append({
                "from": "ina",
                "text": ai_response,
                "brain_action": brain_action,
                "brain_key": brain_key,
                "bot_offer": result.get("counter_price") if result else None
            })

            updated_session = latest_session.model_dump()
            updated_session["messages"] = history
            await state_manager.set_session(redis_key, updated_session)

        return ChatOutput(response=ai_response, is_fallback=is_fallback)

    except HTTPException:
        raise

    except TimeoutError:
        logger.warning(
            "Session lock timeout for user_id=%s", payload.user_id
        )
        raise HTTPException(
            status_code=409,
            detail={"error": True, "code": "SESSION_LOCKED", "message": "Another request is already processing this session. Please retry."},
        )

    except Exception as e:
        logger.exception(
            "Unexpected error for session %s: %s", payload.user_id, e
        )
        raise HTTPException(status_code=500, detail={"error": True, "code": "INTERNAL_ERROR", "message": "Internal server error"})
