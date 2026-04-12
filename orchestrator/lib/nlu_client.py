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

logger = logging.getLogger("nlu_client")

NLU_URL = os.getenv("NLU_URL", "http://nlu-service:8000")

# Circuit breaker: opens after 5 failures, recovers after 30s
_breaker = CircuitBreaker("nlu-service", failure_threshold=5, recovery_timeout=30)

# Fallback response when NLU is unavailable
_FALLBACK = {
    "intent": "unknown",
    "entities": {"PRICE": None},
    "sentiment": "neutral",
}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=4),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _call_nlu_with_retry(payload: dict) -> dict:
    """Raw HTTP call to NLU with retry logic. Raises on failure."""
    client = get_http_client()
    resp = await client.post(f"{NLU_URL}/parse", json=payload)
    resp.raise_for_status()
    return resp.json()


async def call_nlu(text: str, session_id: str) -> dict:
    """
    Call the NLU service with:
    - Connection pooling (shared httpx client)
    - Retry with exponential backoff (3 attempts)
    - Circuit breaker (stops calling after 5 consecutive failures)
    - Safe fallback on any failure
    """
    payload = {"text": text, "session_id": session_id}

    try:
        return await _breaker.call(_call_nlu_with_retry, payload)

    except CircuitOpenError:
        logger.warning("NLU circuit OPEN — using fallback")
        return _FALLBACK

    except Exception as e:
        logger.exception(f"NLU failed after retries: {e}")
        return _FALLBACK
