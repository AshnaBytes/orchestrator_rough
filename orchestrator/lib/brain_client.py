import httpx
import logging

logger = logging.getLogger("brain_client")

STRATEGY_ENGINE_URL = "http://strategy-engine:8000"

# Map NLU intents to Strategy Engine intents
INTENT_MAP = {
    "propose_offer": "MAKE_OFFER",
    "ask_question": "ASK_QUESTION",
}


async def call_brain(mam, asking_price, user_offer, user_intent, user_sentiment, session_id, history):
    # --- Safety: Ensure user_offer is always a float ---
    if user_offer is None:
        user_offer = 0.0

    mapped_intent = INTENT_MAP.get(user_intent, user_intent)

    payload = {
        "mam": mam,
        "asking_price": asking_price,
        "user_offer": float(user_offer),
        "user_intent": mapped_intent,
        "user_sentiment": user_sentiment,
        "session_id": session_id,
        "history": history
    }

    logger.info(f"[MS4] Sending payload → Brain: {payload}")

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                f"{STRATEGY_ENGINE_URL}/decide",
                json=payload
            )
            resp.raise_for_status()
            return resp.json()

    except httpx.HTTPStatusError as e:
        # 422 or other HTTP errors
        logger.error(f"[MS4] Brain returned HTTP error {e.response.status_code}: {e}")
        return {
            "action": "ERROR",
            "counter_price": None,
            "response_key": "ENGINE_UNAVAILABLE"
        }

    except Exception as e:
        logger.exception(f"[MS4] Brain error: {e}")
        return {
            "action": "ERROR",
            "counter_price": None,
            "response_key": "ENGINE_UNAVAILABLE"
        }
