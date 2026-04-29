import os
import httpx
import logging

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from orchestrator.lib.http_pool import get_http_client
from orchestrator.lib.circuit_breaker import CircuitBreaker, CircuitOpenError

logger = logging.getLogger("phraser_client")

LLM_PHRASER_URL = os.getenv("LLM_PHRASER_URL", "http://llm-phraser:8000")

# Circuit breaker: opens after 5 failures, recovers after 30s
_breaker = CircuitBreaker("llm-phraser", failure_threshold=5, recovery_timeout=30)

# Fallback when LLM Phraser is down
_FALLBACK = {
    "response_text": "Let me think about that for a moment.",
    "is_fallback": True,
}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=4),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _call_phraser_with_retry(payload: dict, request_id: str = "") -> dict:
    """Raw HTTP call to LLM Phraser with retry logic."""
    client = get_http_client()
    headers = {"X-Request-ID": request_id} if request_id else {}
    resp = await client.post(
        f"{LLM_PHRASER_URL}/api/v1/phrase", json=payload, headers=headers
    )
    resp.raise_for_status()
    data = resp.json()
    data["is_fallback"] = False
    return data


async def call_phraser(
    brain_output: dict, language: str = "english", request_id: str = ""
) -> dict:
    """
    Call the LLM Phraser with:
    - Connection pooling (shared httpx client)
    - Retry with exponential backoff (3 attempts)
    - Circuit breaker (stops calling after 5 consecutive failures)
    - Safe fallback on any failure
    """
    phraser_payload = {
        "action": brain_output.get("action"),
        "response_key": brain_output.get("response_key"),
        "counter_price": brain_output.get("counter_price") or 0,
        "policy_type": brain_output.get("policy_type", "rule-based"),
        "policy_version": brain_output.get("policy_version", "v1"),
        "decision_metadata": brain_output.get("decision_metadata", {}),
        "language": language,
    }

    logger.info(
        "[rid=%s][Phraser] Sending: action=%s key=%s",
        request_id,
        phraser_payload.get("action"),
        phraser_payload.get("response_key"),
    )

    try:
        data = await _breaker.call(
            _call_phraser_with_retry, phraser_payload, request_id
        )
        logger.info(f"[Phraser] RAW RESPONSE ← {data}")
        return data

    except CircuitOpenError:
        logger.warning("Mouth circuit OPEN — using fallback")
        return _FALLBACK

    except Exception as e:
        logger.exception(f"Phraser failed after retries: {e}")
        return _FALLBACK
