import httpx
import logging

logger = logging.getLogger("ms5_client")

LLM_PHRASER_URL = "http://llm-phraser:8000"


async def call_mouth(brain_output: dict):
    """
    MS5 expects the FULL PhraserInput schema.
    """

    ms5_payload = {
        "action": brain_output["action"],
        "response_key": brain_output["response_key"],
        "counter_price": brain_output.get("counter_price"),

        # 🔥 REQUIRED BY SCHEMA
        "policy_type": brain_output.get("policy_type", "rule-based"),
        "policy_version": brain_output.get("policy_version"),
        "decision_metadata": brain_output.get("decision_metadata"),
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{LLM_PHRASER_URL}/phrase",
                json=ms5_payload,
                timeout=10
            )
            resp.raise_for_status()
            return resp.json()

    except Exception as e:
        logger.exception(f"MS5 error: {e}")
        return {"response_text": "Let me think about that for a moment. Could you please try again?"}
