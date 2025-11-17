# src/orchestrator/lib/backend_client.py
import os
import httpx
import logging

logger = logging.getLogger("backend_client")

BACKEND_URL = "https://web-production-d88ec.up.railway.app/api/v1/policy/default/default"
BACKEND_JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZXhwIjoxNzYzMjIwNTAxfQ.xP-mVC6nWAimordbN6zYJHNyq14DA1duG_hrhyjh3V0"   # or real token if required

async def get_rules_from_backend():
    """
    Fetch negotiation rules/policies from the live backend.
    """
    headers = {
        "Authorization": f"Bearer {BACKEND_JWT}",
        "Accept": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(BACKEND_URL, headers=headers)
            response.raise_for_status()  # raise error if 4xx/5xx
            data = response.json()
            logger.info("Fetched rules from backend successfully.")
            return data
    except Exception as e:
        logger.exception(f"Failed to fetch backend rules: {e}")
        return {"error": "Backend unavailable"}
