"""
Lightweight Circuit Breaker for inter-service communication.

States:
    CLOSED   → Normal operation. Requests pass through.
    OPEN     → Service is considered down. Requests immediately fail
               with CircuitOpenError (no network call made).
    HALF_OPEN → After recovery_timeout, allow ONE test request through.
               If it succeeds → CLOSED. If it fails → back to OPEN.

Usage:
    nlu_breaker = CircuitBreaker("nlu-service")

    try:
        result = await nlu_breaker.call(some_async_func, arg1, arg2)
    except CircuitOpenError:
        # Service is down, use fallback
        result = fallback_value
"""

import time
import logging
from enum import Enum
from typing import Any

logger = logging.getLogger("circuit_breaker")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitOpenError(Exception):
    """Raised when the circuit is open and calls are being blocked."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        super().__init__(
            f"Circuit breaker OPEN for '{service_name}' — "
            f"service is temporarily unavailable."
        )


class CircuitBreaker:
    """
    A simple async circuit breaker.

    Args:
        name: Identifier for logging (e.g. "nlu-service")
        failure_threshold: Consecutive failures before opening the circuit.
        recovery_timeout: Seconds to wait before trying a test request.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0

    @property
    def state(self) -> CircuitState:
        """Current circuit state (with automatic OPEN → HALF_OPEN transition)."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                logger.info(
                    "[%s] Recovery timeout elapsed (%.1fs) — transitioning to HALF_OPEN",
                    self.name,
                    elapsed,
                )
                self._state = CircuitState.HALF_OPEN
        return self._state

    async def call(self, func, *args, **kwargs) -> Any:
        """
        Execute an async function through the circuit breaker.

        Raises CircuitOpenError if the circuit is open.
        On success → resets failure count (closes circuit if half-open).
        On failure → increments failure count (opens circuit if threshold hit).
        """
        current_state = self.state  # triggers OPEN → HALF_OPEN check

        if current_state == CircuitState.OPEN:
            logger.warning(
                "[%s] Circuit OPEN — blocking call (%.0fs until recovery)",
                self.name,
                self.recovery_timeout - (time.monotonic() - self._last_failure_time),
            )
            raise CircuitOpenError(self.name)

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result

        except Exception:
            self._on_failure()
            raise

    def _on_success(self):
        """Reset on success. If HALF_OPEN → close the circuit."""
        if self._state == CircuitState.HALF_OPEN:
            logger.info("[%s] HALF_OPEN test succeeded — circuit CLOSED", self.name)
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def _on_failure(self):
        """Increment failure count. Open circuit if threshold reached."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.error(
                "[%s] %d consecutive failures — circuit OPEN (blocking for %.0fs)",
                self.name,
                self._failure_count,
                self.recovery_timeout,
            )
        else:
            logger.warning(
                "[%s] Failure %d/%d",
                self.name,
                self._failure_count,
                self.failure_threshold,
            )

    def reset(self):
        """Manually reset the circuit breaker (for testing)."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
