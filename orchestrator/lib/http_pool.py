"""
Shared HTTP connection pool for inter-service communication.

Problem (before):
    Every request created a new httpx.AsyncClient → new TCP connection
    → TCP handshake overhead → socket exhaustion under load.

Solution:
    Singleton AsyncClient with connection pooling. All service clients
    (NLU, Brain, Mouth) share this pool. Connections are reused across
    requests via HTTP keep-alive.

Usage:
    from orchestrator.lib.http_pool import get_http_client, close_http_client

    client = get_http_client()
    resp = await client.post(url, json=payload)

    # On app shutdown:
    await close_http_client()
"""

import os
import logging
import httpx

logger = logging.getLogger("http_pool")

INTERNAL_KEY = os.getenv("INTERNAL_SERVICE_KEY", "")

_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """
    Return a singleton httpx.AsyncClient with connection pooling.

    The client is created lazily on first call and reused for all
    subsequent requests. The shared X-Internal-Key header is set
    once here — no need to pass it in every client call.
    """
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=5.0,  # max time to establish TCP connection
                read=15.0,  # max time waiting for response body
                write=5.0,  # max time sending request body
                pool=10.0,  # max time waiting for a connection from the pool
            ),
            limits=httpx.Limits(
                max_connections=100,  # total concurrent connections
                max_keepalive_connections=20,  # idle connections kept alive
                keepalive_expiry=30,  # seconds before idle connection is closed
            ),
            headers={"X-Internal-Key": INTERNAL_KEY},
        )
        logger.info("HTTP connection pool created (max_conn=100, keepalive=20)")
    return _client


async def close_http_client():
    """Gracefully close the HTTP client pool. Call on app shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("HTTP connection pool closed")
