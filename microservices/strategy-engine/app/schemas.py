# Purpose: Defines the data contracts (schemas) for your API.
# (Upgraded to v1.1)

from pydantic import BaseModel, Field, ConfigDict  # <-- Import ConfigDict
from typing import Literal, List, Dict, Any, Optional

# =======================================================================
#  API Input Schema (v1.1)
# =======================================================================

class StrategyInput(BaseModel):
    """
    The data payload sent FROM the Dialogue Orchestrator (MS 1)
    TO this service (MS 4: The Brain).
    
    v1.1 Update: Now includes 'user_intent' and 'user_sentiment'
    from the NLU Pipeline (MS 2).
    """
    
    # Core Financial Data (THE SECRET)
    mam: float = Field(
        ...,
        description="Minimum Acceptable Margin. The secret financial floor."
    )
    
    # Contextual Negotiation Data
    asking_price: float = Field(
        ..., 
        description="The initial price listed or offered by the business."
    )
    user_offer: float = Field(
        ..., 
        description="The latest price offered by the user."
    )
    
    # --- NEW FIELDS (from MS 2: NLU) ---
    user_intent: str = Field(
        ...,
        description="The user's detected intent (e.g., 'MAKE_OFFER', 'ASK_QUESTION')."
    )
    user_sentiment: str = Field(
        ...,
        description="The user's detected sentiment (e.g., 'positive', 'negative', 'neutral')."
    )
    
    # Dialogue & State
    session_id: str = Field(
        ..., 
        description="Unique identifier for the negotiation session."
    )
    history: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Log of conversation turns"
    )

    # --- Pydantic v2 Update ---
    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "mam": 42000.0,
                "asking_price": 50000.0,
                "user_offer": 45000.0,
                "user_intent": "MAKE_OFFER",      # <-- New
                "user_sentiment": "positive",   # <-- New
                "session_id": "sess_12345abc",
                "history": [
                    {"role": "bot", "action": "GREET"},
                    {"role": "user", "offer": 45000.0}
                ]
            }
        }
    )

# =======================================================================
#  API Output Schema
# =======================================================================

class StrategyOutput(BaseModel):
    """
    The data payload (a 'command') sent FROM this service (MS 4)
    TO the Dialogue Orchestrator (MS 1).
    """
    
    action: Literal["ACCEPT", "REJECT", "COUNTER"] = Field(
        ..., 
        description="The negotiation action to take."
    )
    response_key: str = Field(
        ..., 
        description="A structured key for MS 5 to select the right response template."
    )
    counter_price: Optional[float] = Field(
        default=None, 
        description="The new price to offer (if action is COUNTER)."
    )
    
    # --- Hooks for Future RL Integration ---
    policy_type: str = Field(
        default="rule-based",
        description="The type of policy that made this decision."
    )
    policy_version: Optional[str] = Field(
        default="1.0.0",
        description="The version of the policy used."
    )
    decision_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional data for audit/logging."
    )

    # --- Pydantic v2 Update ---
    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "action": "COUNTER",
                "response_key": "STANDARD_COUNTER",
                "counter_price": 48000.0,
                "policy_type": "rule-based",
                "policy_version": "1.1.0",
                "decision_metadata": {"reason": "User offer > 70% of MAM, applying mid-point formula."}
            }
        }
    )