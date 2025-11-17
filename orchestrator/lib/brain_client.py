import httpx
import logging

logger = logging.getLogger("brain_client")

STRATEGY_ENGINE_URL = "http://strategy-engine:8001/decide"

INTENT_MAP = {
    "propose_offer": "MAKE_OFFER",
    "ask_question": "ASK_QUESTION",
}

async def call_brain(mam, asking_price, user_offer, user_intent, user_sentiment, session_id, history):
    mapped_intent = INTENT_MAP.get(user_intent, user_intent)

    payload = {
        "mam": mam,
        "asking_price": asking_price,
        "user_offer": user_offer,
        "user_intent": mapped_intent,
        "user_sentiment": user_sentiment,
        "session_id": session_id,
        "history": history
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{STRATEGY_ENGINE_URL}/decide", json=payload)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.exception(f"Brain error: {e}")
        return {
            "action": "ERROR",
            "counter_price": None,
            "response_key": "ENGINE_UNAVAILABLE"
        }
