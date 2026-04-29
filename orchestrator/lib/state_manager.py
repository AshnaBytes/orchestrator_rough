# src/orchestrator/lib/state_manager.py
import os
import json
import logging
import asyncio
from uuid import uuid4
from contextlib import asynccontextmanager
from typing import Optional

# Use redis.asyncio client (redis-py supports asyncio)
try:
    import redis.asyncio as redis  # type: ignore
except Exception:
    # Fall back to sync redis package to silence static import resolution errors in editors;
    # runtime code expects the asyncio client from redis-py (redis.asyncio), so ensure the
    # correct package is installed in deployment/runtime.
    import redis  # type: ignore

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL")
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
        if REDIS_URL:
            _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        else:
            _redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                decode_responses=True,  # returns strings not bytes
            )
    return _redis_client


async def set_session(
    session_id: str, data: dict, expire: int = REDIS_EXPIRE_SECONDS
) -> bool:
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


async def _release_lock(lock_key: str, token: str) -> None:
    """
    Release lock only if token matches (safe unlock).
    """
    client = get_redis_client()
    release_script = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        return redis.call("DEL", KEYS[1])
    else
        return 0
    end
    """
    try:
        await client.eval(release_script, 1, lock_key, token)
    except Exception as exc:
        logger.warning("Failed to release lock %s: %s", lock_key, exc)


@asynccontextmanager
async def session_lock(
    session_id: str,
    acquire_timeout: float = 3.0,
    lock_ttl: int = 10,
):
    """
    Redis distributed lock per session to prevent concurrent lost updates.

    - acquire_timeout: max seconds to wait for lock.
    - lock_ttl: lock expiry to avoid deadlocks if process crashes.
    """
    from fastapi import HTTPException  # local import to avoid circular dep

    client = get_redis_client()
    lock_key = f"lock:{session_id}"
    token = str(uuid4())
    deadline = asyncio.get_event_loop().time() + acquire_timeout
    acquired = False

    while asyncio.get_event_loop().time() < deadline:
        try:
            acquired = bool(await client.set(lock_key, token, nx=True, ex=lock_ttl))
        except Exception as exc:
            logger.exception("Error acquiring lock %s: %s", lock_key, exc)
            acquired = False

        if acquired:
            break
        await asyncio.sleep(0.05)

    if not acquired:
        logger.warning(
            "Could not acquire lock for session %s — concurrent request in progress",
            session_id,
        )
        raise HTTPException(
            status_code=429,
            detail="Another request is already being processed for this session. Please retry in a moment.",
        )

    try:
        yield
    finally:
        await _release_lock(lock_key, token)
