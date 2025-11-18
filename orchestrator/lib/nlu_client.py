import httpx
import logging

logger = logging.getLogger("nlu_client")

NLU_URL = "http://nlu-service:8000/parse"


async def call_nlu(text: str, session_id: str):
    payload = {
        "text": text,
        "session_id": session_id
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(NLU_URL, json=payload)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.exception(f"NLU error: {e}")
        return {
            "intent": "unknown",
            "entities": {"PRICE": None},
            "sentiment": "neutral"
        }
