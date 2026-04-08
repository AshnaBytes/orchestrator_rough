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
_FALLBACK = {"response_text": "Let me think about that for a moment."}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=4),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _call_phraser_with_retry(payload: dict) -> dict:
    """Raw HTTP call to LLM Phraser with retry logic."""
    client = get_http_client()
    resp = await client.post(f"{LLM_PHRASER_URL}/phrase", json=payload)
    resp.raise_for_status()
    return resp.json()


async def call_phraser(brain_output: dict) -> dict:
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
    }

    logger.info(f"[Phraser] Sending payload: {phraser_payload}")

    try:
        data = await _breaker.call(_call_phraser_with_retry, phraser_payload)
        logger.info(f"[Phraser] RAW RESPONSE ← {data}")
        return data

    except CircuitOpenError:
        logger.warning("Mouth circuit OPEN — using fallback")
        return _FALLBACK

    except Exception as e:
        logger.exception(f"Phraser failed after retries: {e}")
        return _FALLBACK
