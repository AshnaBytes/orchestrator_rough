"""
NLU Service (MS2) — INA Negotiation Chatbot

NLU Pipeline:
    Primary:  LangChain + Groq (llama-3.1-8b-instant) with structured output
              → Handles natural language prices, context-aware intent
    Fallback: Regex pipeline (same as original)
              → Kicks in if Groq/LangChain is unavailable
"""

import os
import re
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from .schemas import NLUInput, NLUOutput
from . import llm_nlu

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------- Config ----------------------
INTERNAL_KEY = os.getenv("INTERNAL_SERVICE_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


# ---------------------- Lifespan ----------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the LangChain NLU chain once on startup."""
    if not GROQ_API_KEY:
        logger.error("FATAL: GROQ_API_KEY is not set. LLM NLU will always fallback to regex.")
        app.state.nlu_chain = None
    else:
        app.state.nlu_chain = llm_nlu.build_nlu_chain(GROQ_API_KEY)
        logger.info("NLU service started — LangChain + Groq chain initialized.")
    yield
    logger.info("NLU service shutting down.")


app = FastAPI(title="NLU Service (MS2)", lifespan=lifespan)


# ---------------------- Auth Middleware ----------------------
@app.middleware("http")
async def verify_internal_key(request: Request, call_next):
    """
    Verify that incoming requests carry the correct X-Internal-Key header.
    Health check and docs endpoints are exempt.
    """
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
# 🔁 Regex Fallback (preserved from original)
# Used when the LLM call fails for any reason.
# =====================================================
def _regex_fallback(text: str) -> dict:
    """
    Original regex-based NLU pipeline.
    Returns same shape as llm_nlu.parse() result.
    """
    text_lower = text.lower()

    # --- Price Extraction (improved: requires 2+ digits) ---
    price_match = re.search(r"\$?\s*(\d{2,}(?:[.,]\d+)?)", text_lower)
    price = float(price_match.group(1).replace(",", "")) if price_match else None

    # --- Intent Detection ---
    def contains_word(t, words):
        pattern = r"\b(" + "|".join(re.escape(w) for w in words) + r")\b"
        return re.search(pattern, t) is not None

    greetings = ["hi", "hello", "hey"]
    farewells = ["bye", "goodbye", "see you", "later"]
    deal_words = ["deal", "accept", "agree"]
    prev_queries = ["earlier price", "previous offer", "last offer", "previous counter"]

    if contains_word(text_lower, greetings):
        intent = "GREET"
    elif contains_word(text_lower, farewells):
        intent = "BYE"
    elif any(w in text_lower for w in deal_words):
        intent = "DEAL"
    elif any(w in text_lower for w in prev_queries):
        intent = "ASK_PREVIOUS_OFFER"
    elif price:
        intent = "MAKE_OFFER"
    else:
        intent = "ASK_QUESTION"

    # --- Sentiment Detection ---
    negative_words = ["high", "expensive", "unfair", "bad", "angry", "upset", "worst", "frustrated"]
    positive_words = ["good", "great", "happy", "perfect", "amazing", "love"]

    if any(w in text_lower for w in negative_words):
        sentiment = "negative"
    elif any(w in text_lower for w in positive_words):
        sentiment = "positive"
    else:
        sentiment = "neutral"

    return {"intent": intent, "price": price, "sentiment": sentiment}


# =====================================================
# 🔍 PARSE ENDPOINT
# =====================================================
@app.post("/parse", response_model=NLUOutput)
async def parse(input: NLUInput):
    """
    Parse user text into structured NLU output.

    Layer 1: Python pre-check — fast, zero-cost detection of obvious invalid inputs.
             Passes a descriptive hint to the LLM rather than hard-coding a fixed message.
    Layer 2: LLM — classifies intent and generates a unique, contextual error message.
    """
    # ------------------------------------------------------------------
    # LAYER 1: Python Pre-Check (Zero Token Cost)
    # Detects obvious invalids and gives LLM a hint to generate a smart,
    # dynamic error message. Does NOT hard-code the final response.
    # ------------------------------------------------------------------
    text = input.text.strip()
    hint = ""

    if not text:
        hint = "empty_input"
    elif re.search(r'\d+\s*[\+\-\*/]\s*\d+', text) or re.search(r'\b(divide|divided by|plus|minus|times|multiplied by|fraction)\b', text, re.IGNORECASE) or re.search(r'\b[a-z]\s*=\s*\d', text, re.IGNORECASE):
        hint = "math_expression_detected"
    elif re.search(r'-\s*\$?\s*\d+', text):
        hint = "negative_number_detected"
    elif not re.search(r'[a-zA-Z0-9]', text):
        hint = "gibberish_no_alphanumeric"

    if hint:
        logger.info("[NLU Layer 1] Pre-check flagged input. Hint: %s", hint)

    # ------------------------------------------------------------------
    # LAYER 2: LLM Smart Judge (passes hint for contextual error message)
    # ------------------------------------------------------------------
    chain = app.state.nlu_chain

    if chain is not None:
        try:
            result = await llm_nlu.parse(input.text, chain, hint=hint)
            # --- CAVE-MAN ULTRA: Layer 1 override ---
            # If our fast pre-check found an issue, we FORCE the intent to INVALID.
            # This prevents the LLM from "being too smart" and trying to process math.
            if hint:
                logger.warning("[NLU Layer 1 Override] Hint was present (%s). Forcing INVALID.", hint)
                result["intent"] = "INVALID"
                if not result.get("error_message"):
                    result["error_message"] = "I'm sorry, I couldn't process that input. Please provide a clear price."
        except Exception as e:
            logger.warning("[NLU] LLM parse failed — using regex fallback. Error: %s", e)
            result = _regex_fallback(input.text)
    else:
        logger.warning("[NLU] No LLM chain available — using regex fallback.")
        result = _regex_fallback(input.text)

    return NLUOutput(
        intent=result["intent"],
        entities={"PRICE": result["price"] if result["intent"] != "INVALID" else None},
        sentiment=result["sentiment"],
        language=result.get("language", "english"),
        error_message=result.get("error_message"),
    )
