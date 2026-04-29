"""
Session data validation schemas.

The monolith backend creates sessions in Redis after validating
the tenant's API key. This module defines the expected structure
of that session data so the orchestrator can validate it on every
chat request — acting as a security boundary.

Expected Redis session format (JSON):
{
    "mam": 150.0,
    "asking_price": 200.0,
    "messages": [],
    "offer_count": 0,
    "status": "negotiating",
    "last_bot_offer": null,
    "tenant_id": "tenant_abc",       # optional
    "product_id": "prod_xyz",        # optional
    "created_at": "2026-04-08T..."   # optional
}
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class SessionData(BaseModel):
    """
    Validates the structure of session data stored in Redis.

    Required fields (mam, asking_price, messages) MUST be present —
    if any are missing, the session is considered corrupt/invalid
    and the request will be rejected with 401.
    """

    # --- Required Business Data (written by the monolith) ---
    mam: float = Field(
        ...,
        description="Minimum Acceptable Margin — the secret financial floor.",
    )
    asking_price: float = Field(
        ...,
        description="The listed/initial price for the product.",
    )
    messages: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Conversation history for this session.",
    )

    # --- Offer Limit & Lock State (managed by the orchestrator) ---
    offer_count: int = Field(
        default=0,
        description="Number of valid monetary offers made by the user so far.",
    )
    status: str = Field(
        default="negotiating",
        description="Session status: 'negotiating' or 'locked'.",
    )
    last_bot_offer: Optional[float] = Field(
        default=None,
        description="The last counter-offer made by the bot. Returned as final price after lock.",
    )

    # --- Optional Metadata (useful for logging/analytics) ---
    tenant_id: Optional[str] = Field(
        default=None,
        description="ID of the tenant who owns this session.",
    )
    product_id: Optional[str] = Field(
        default=None,
        description="ID of the product being negotiated.",
    )
    created_at: Optional[str] = Field(
        default=None,
        description="ISO timestamp of when the session was created.",
    )
