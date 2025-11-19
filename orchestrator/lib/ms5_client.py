import httpx
import logging

logger = logging.getLogger("ms5_client")

LLM_PHRASER_URL = "http://llm-phraser:8000"

print("🔥 LOADED ms5_client: NEW VERSION")


async def call_mouth(brain_output: dict):
    """
    MS5 ONLY accepts:
    - action
    - counter_price
    - response_key
    """

    ms5_payload = {
        "action": brain_output["action"],
        "counter_price": brain_output.get("counter_price"),
        "response_key": brain_output["response_key"],
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{LLM_PHRASER_URL}/phrase",
                json=ms5_payload
            )
            resp.raise_for_status()
            return resp.json()

    except Exception as e:
        logger.exception(f"MS5 error: {e}")
        return {"response_text": "[SYSTEM] Could not generate phrase."}
