"""
NLU Service (MS2) — INA Negotiation Chatbot

NLU Pipeline:
    Primary:  DSPy + Groq (llama-3.3-70b-versatile) with BootstrapFewShot
              compiled program — handles all validation end-to-end.
    Fallback: Minimal deterministic fallback for user-facing resilience.
              Returns UNKNOWN intent with HTTP 200 so the caller can degrade
              gracefully rather than showing a hard error to the user.
"""

import os
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from .schemas import NLUInput, NLUOutput
from . import dspy_nlu

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------- Config ----------------------
INTERNAL_KEY = os.getenv("INTERNAL_SERVICE_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


# ---------------------- Lifespan ----------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the DSPy NLU module once on startup."""
    if not OPENAI_API_KEY and not GROQ_API_KEY:
        logger.error(
            "FATAL: Neither OPENAI_API_KEY nor GROQ_API_KEY is set. "
            "NLU will always use the deterministic fallback."
        )
        app.state.nlu_module = None
    else:
        app.state.nlu_module = dspy_nlu.build_nlu_module(OPENAI_API_KEY, GROQ_API_KEY)
        logger.info("NLU service started — DSPy module initialized.")
    yield
    logger.info("NLU service shutting down.")


app = FastAPI(title="NLU Service (MS2)", lifespan=lifespan)

# Prometheus Instrumentation
Instrumentator().instrument(app).expose(app)


# ---------------------- Auth Middleware ----------------------
@app.middleware("http")
async def verify_internal_key(request: Request, call_next):
    if request.url.path in ("/health", "/", "/docs", "/openapi.json"):
        return await call_next(request)

    incoming_key = request.headers.get("X-Internal-Key", "")
    if not INTERNAL_KEY or incoming_key != INTERNAL_KEY:
        logger.warning("Unauthorized request to %s — key mismatch", request.url.path)
        return JSONResponse(
            status_code=403,
            content={"detail": "Forbidden: Invalid internal service key."},
        )

    return await call_next(request)


# ---------------------- Health ----------------------
@app.get("/health", status_code=200)
async def health_check():
    return {"status": "ok", "service": "nlu-service"}


# =====================================================
# Deterministic Fallback
# Used only when DSPy/Groq is completely unavailable.
# Returns a safe, minimal result that lets the caller
# degrade gracefully instead of crashing the user flow.
# =====================================================
def _deterministic_fallback(text: str) -> dict:
    """
    Minimal rule-based fallback.  Intentionally conservative:
    - Detects a plain numeric offer (2+ digits) → MAKE_OFFER
    - Detects simple greet/bye/deal keywords
    - Everything else → ASK_QUESTION (safe neutral intent)
    No INVALID classification here — that requires LLM reasoning.
    """
    t = text.lower().strip()

    greetings = r"\b(hi|hello|hey|salam|salam alaikum)\b"
    farewells = r"\b(bye|goodbye|khuda hafiz|alvida)\b"
    deal_words = r"\b(deal|agreed|accept|theek hai deal|done)\b"
    price_pat = r"\$?\s*(\d{2,}(?:[.,]\d+)?)"

    if re.search(greetings, t):
        intent, price = "GREET", None
    elif re.search(farewells, t):
        intent, price = "BYE", None
    elif re.search(deal_words, t):
        intent, price = "DEAL", None
    else:
        m = re.search(price_pat, t)
        if m:
            intent = "MAKE_OFFER"
            price = float(m.group(1).replace(",", ""))
        else:
            intent, price = "ASK_QUESTION", None

    return {
        "intent": intent,
        "price": price,
        "sentiment": "neutral",
        "language": "english",  # can't detect language without LLM
        "error_message": None,
    }


# =====================================================
# PARSE ENDPOINT  — contract unchanged
# =====================================================
@app.post("/api/v1/parse", response_model=NLUOutput)
async def parse(input: NLUInput):
    """
    Parse user text into structured NLU output.

    All validation (math, barter, gibberish, negative numbers, etc.)
    is handled end-to-end by the DSPy module — no Layer 1 pre-checks.
    """
    module = app.state.nlu_module

    if module is not None:
        try:
            result = await dspy_nlu.parse(input.text, module)
        except Exception as e:
            logger.warning("[NLU] DSPy parse failed — using fallback. Error: %s", e)
            result = _deterministic_fallback(input.text)
    else:
        logger.warning("[NLU] No DSPy module available — using fallback.")
        result = _deterministic_fallback(input.text)

    return NLUOutput(
        intent=result["intent"],
        entities={"PRICE": result["price"]},
        sentiment=result["sentiment"],
        language=result["language"],
        error_message=result.get("error_message"),
    )
