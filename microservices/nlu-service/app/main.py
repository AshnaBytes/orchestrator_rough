import os
import re
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------- Internal Service Key ----------------------
INTERNAL_KEY = os.getenv("INTERNAL_SERVICE_KEY", "")

app = FastAPI(title="NLU Service (MS2)")


# ---------------------- Auth Middleware ----------------------
@app.middleware("http")
async def verify_internal_key(request: Request, call_next):
    """
    Verify that incoming requests carry the correct X-Internal-Key header.
    Health check endpoint is exempt so Docker/k8s healthchecks still work.
    """
    # Allow health checks without auth
    if request.url.path in ("/health", "/", "/docs", "/openapi.json"):
        return await call_next(request)

    # Verify the key
    incoming_key = request.headers.get("X-Internal-Key", "")
    if not INTERNAL_KEY or incoming_key != INTERNAL_KEY:
        logger.warning(f"Unauthorized request to {request.url.path} — key mismatch")
        return JSONResponse(
            status_code=403,
            content={"detail": "Forbidden: Invalid internal service key."},
        )

    return await call_next(request)


from .schemas import NLUInput, NLUOutput


# ---------------------- Health ----------------------
@app.get("/health", status_code=200)
async def health_check():
    return {"status": "ok", "service": "nlu-service"}


# ---------------------- Parse Endpoint ----------------------
@app.post("/parse", response_model=NLUOutput)
async def parse(input: NLUInput):
    text = input.text.lower()

    # -------------------------
    # 1️⃣ PRICE Extraction
    # -------------------------
    price_match = re.search(r"(\d+)", text)
    price = float(price_match.group(1)) if price_match else None

    # -------------------------
    # 2️⃣ Intent Detection
    # -------------------------
    greetings = ["hi", "hello", "hey"]
    farewells = ["bye", "goodbye", "see you", "later"]
    deal_words = ["deal", "accept", "agree"]
    previous_offer_queries = ["earlier price", "previous offer", "last offer", "previous counter", "previous deal"]

    # Use regex for word boundary matching to avoid partial matches (e.g., "this" -> "hi")
    def contains_word(text, words):
        pattern = r"\b(" + "|".join(re.escape(w) for w in words) + r")\b"
        return re.search(pattern, text) is not None

    if contains_word(text, greetings):
        intent = "GREET"
    elif contains_word(text, farewells):
        intent = "BYE"
    elif any(word in text for word in deal_words):
        intent = "DEAL"
    elif any(word in text for word in previous_offer_queries):
        intent = "ASK_PREVIOUS_OFFER"
    elif price:
        intent = "MAKE_OFFER"
    else:
        intent = "ASK_QUESTION"


    # -------------------------
    # 3️⃣ Sentiment Detection
    # -------------------------
    def detect_sentiment(text: str) -> str:
        text = text.lower()
        negative_words = ["high", "disappointed","expensive", "unfair", "bad", "angry", "upset", "worst", "frustrated", "annoyed"]
        positive_words = ["good", "great", "happy", "perfect", "amazing", "love"]

        if any(w in text for w in negative_words):
            return "negative"
        if any(w in text for w in positive_words):
            return "positive"
        else:
            return "neutral"

    sentiment = detect_sentiment(text)

    return {
        "intent": intent,
        "entities": {"PRICE": price},
        "sentiment": sentiment,
    }
