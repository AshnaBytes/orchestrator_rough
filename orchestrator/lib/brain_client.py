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

logger = logging.getLogger("brain_client")

STRATEGY_ENGINE_URL = os.getenv("STRATEGY_ENGINE_URL", "http://strategy-engine:8000")


# Circuit breaker: opens after 5 failures, recovers after 30s
_breaker = CircuitBreaker("strategy-engine", failure_threshold=5, recovery_timeout=30)


def _build_fallback(asking_price: float) -> dict:
    """Safe fallback when Brain is unavailable — stick to asking price."""
    return {
        "action": "COUNTER",
        "counter_price": asking_price,
        "response_key": "ENGINE_UNAVAILABLE",
        "policy_type": "rule-based",
        "policy_version": "fallback",
        "decision_metadata": {"reason": "brain_unavailable"},
        "is_fallback": True,
    }


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=4),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _call_brain_with_retry(payload: dict, request_id: str = "") -> dict:
    """Raw HTTP call to Strategy Engine with retry logic."""
    client = get_http_client()
    headers = {"X-Request-ID": request_id} if request_id else {}
    resp = await client.post(
        f"{STRATEGY_ENGINE_URL}/api/v1/decide", json=payload, headers=headers
    )
    resp.raise_for_status()
    data = resp.json()
    data["is_fallback"] = False
    return data


async def call_brain(
    mam,
    asking_price,
    user_offer,
    user_intent,
    user_sentiment,
    session_id,
    history,
    request_id: str = "",
) -> dict:
    """
    Call the Strategy Engine with:
    - Connection pooling (shared httpx client)
    - Retry with exponential backoff (3 attempts)
    - Circuit breaker (stops calling after 5 consecutive failures)
    - Safe fallback on any failure
    """
    if user_offer is None:
        user_offer = 0.0

    # NLU is the source of truth — pass intent directly, no mapping
    payload = {
        "mam": mam,
        "asking_price": asking_price,
        "user_offer": float(user_offer),
        "user_intent": user_intent,
        "user_sentiment": user_sentiment,
        "session_id": session_id,
        "history": history,
    }

    logger.info(
        "[rid=%s][MS4] Sending to Brain: session=%s, intent=%s, offer=%s",
        request_id,
        session_id,
        user_intent,
        user_offer,
    )

    try:
        return await _breaker.call(_call_brain_with_retry, payload, request_id)

    except CircuitOpenError:
        logger.warning("Brain circuit OPEN — using fallback")
        return _build_fallback(asking_price)

    except httpx.HTTPStatusError as e:
        logger.error(f"[MS4] Brain HTTP error {e.response.status_code}: {e}")
        return _build_fallback(asking_price)

    except Exception as e:
        logger.exception(f"[MS4] Brain failed after retries: {e}")
        return _build_fallback(asking_price)
