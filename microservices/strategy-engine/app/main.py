# Purpose: Initializes the FastAPI application and defines API endpoints.

import os
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from .schemas import StrategyInput, StrategyOutput
from .strategy_core import make_decision
from prometheus_fastapi_instrumentator import Instrumentator

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------- Internal Service Key ----------------------
INTERNAL_KEY = os.getenv("INTERNAL_SERVICE_KEY", "")

# Initialize the FastAPI app
app = FastAPI(
    title="INA Strategy Engine (MS 4 - The Brain)",
    description="This service receives financial context and user offers, "
    "then securely decides the next negotiation step.",
    version="1.0.0",
)

# Prometheus Instrumentation
Instrumentator().instrument(app).expose(app)


# ---------------------- Auth Middleware ----------------------
@app.middleware("http")
async def verify_internal_key(request: Request, call_next):
    """
    Verify that incoming requests carry the correct X-Internal-Key header.
    Health check endpoint is exempt so Docker/k8s healthchecks still work.
    """
    if request.url.path in ("/health", "/", "/docs", "/openapi.json"):
        return await call_next(request)

    incoming_key = request.headers.get("X-Internal-Key", "")
    if not INTERNAL_KEY or incoming_key != INTERNAL_KEY:
        logger.warning(f"Unauthorized request to {request.url.path} — key mismatch")
        return JSONResponse(
            status_code=403,
            content={"detail": "Forbidden: Invalid internal service key."},
        )

    return await call_next(request)


# --- Health Check Endpoint ---
@app.get("/health", status_code=200)
async def health_check():
    """
    Simple health check to confirm the service is running.
    """
    return {"status": "ok", "service": "strategy-engine"}


# --- Strategy Endpoint ---
@app.post("/api/v1/decide", response_model=StrategyOutput)
async def decide_strategy(input_data: StrategyInput):
    """
    Main strategy endpoint.
    Receives the current negotiation state and financial data,
    and returns a secure, non-LLM decision.
    """
    try:
        logger.info(f"Received request for session: {input_data.session_id}")

        decision = make_decision(input_data)

        logger.info(f"Decision for {input_data.session_id}: {decision.action}")
        return decision

    except Exception as e:
        logger.error(
            f"Error during decision for {input_data.session_id}: {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")
