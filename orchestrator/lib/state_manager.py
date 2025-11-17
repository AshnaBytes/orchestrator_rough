# src/orchestrator/lib/state_manager.py
import os
import json
import logging
from typing import Optional
import asyncio

# Use redis.asyncio client (redis-py supports asyncio)
try:
    import redis.asyncio as redis  # type: ignore
except Exception:
    # Fall back to sync redis package to silence static import resolution errors in editors;
    # runtime code expects the asyncio client from redis-py (redis.asyncio), so ensure the
    # correct package is installed in deployment/runtime.
    import redis  # type: ignore

logger = logging.getLogger("state_manager")

logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")  # docker compose service name
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_EXPIRE_SECONDS = int(os.getenv("REDIS_EXPIRE_SECONDS", 60 * 60))  # default 1 hour

# Create the redis client (connection pool)
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    """Return a singleton redis client instance (async)."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True,  # returns strings not bytes
        )
    return _redis_client


async def set_session(session_id: str, data: dict, expire: int = REDIS_EXPIRE_SECONDS) -> bool:
    """
    Save a session dict to Redis (JSON serialized).
    Returns True on success, False on failure.
    """
    client = get_redis_client()
    logger.info(f"Setting session: {session_id}")
    try:
        payload = json.dumps(data)
        await client.set(session_id, payload, ex=expire)
        logger.debug("Set session %s", session_id)
        return True
    except Exception as exc:
        logger.exception("Error setting session %s: %s", session_id, exc)
        return False


async def get_session(session_id: str) -> Optional[dict]:
    """
    Retrieve a session dict from Redis, or None if not found.
    """
    client = get_redis_client()
    logger.info(f"Getting session: {session_id}")
    try:
        raw = await client.get(session_id)
        if raw is None:
            logger.debug("Session %s not found", session_id)
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.exception("Error getting session %s: %s", session_id, exc)
        return None


async def ping_redis() -> bool:
    """
    Check if Redis is reachable (PING).
    """
    client = get_redis_client()
    try:
        res = await client.ping()
        logger.debug("Redis PING -> %s", res)
        return bool(res)
    except Exception as exc:
        logger.exception("Redis ping failed: %s", exc)
        return False


# optional: a graceful close helper (useful on app shutdown)
async def close_redis():
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.close()
            await _redis_client.connection_pool.disconnect()
        except Exception:
            pass
        _redis_client = None
