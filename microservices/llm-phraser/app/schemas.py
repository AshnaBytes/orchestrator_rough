# E:\FYP\llm-phraser\app\schemas.py
# Purpose: Defines the data contracts for the LLM Phraser (MS 5).
# (Updated to Pydantic v2 ConfigDict)

from pydantic import BaseModel, Field, ConfigDict  # <-- Import ConfigDict
from typing import Literal, Dict, Any, Optional

# =======================================================================
#  API Input Schema (THE FIREWALL)
# =======================================================================

class PhraserInput(BaseModel):
    """
    The data payload sent FROM the Orchestrator (originating from MS 4)
    TO this service (MS 5: The Mouth).
    
    This schema *IS* the security boundary. It is structurally
    impossible for 'mam' or other secrets to be passed in.
    """
    
    # The command from MS 4 (The Brain)
    action: Literal["ACCEPT", "REJECT", "COUNTER"] = Field(
        ..., 
        description="The negotiation action to take."
    )
    
    # The key for this service to select the right prompt
    response_key: str = Field(
        ..., 
        description="A structured key to select the response template."
    )
    
    # Optional field, only present if action is 'COUNTER'
    counter_price: Optional[float] = Field(
        default=None, 
        description="The new price to offer (if action is COUNTER)."
    )
    
    # --- Auditing & Metadata (from MS 4) ---
    policy_type: str = Field(
        ...,
        description="The type of policy that made this decision."
    )
    
    policy_version: Optional[str] = Field(
        default=None,
        description="The version of the policy used."
    )
    
    decision_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional data for audit/logging from MS 4."
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
                "decision_metadata": {"rule": "standard_counter_midpoint"}
            }
        }
    )

# =======================================================================
#  API Output Schema
# =======================================================================

class PhraserOutput(BaseModel):
    """
    The data payload sent FROM this service (MS 5)
    TO the Dialogue Orchestrator (MS 1), to be shown to the user.
    """
    
    response_text: str = Field(
        ..., 
        description="The final, AI-generated, persuasive text response."
    )
    
    # --- Pydantic v2 Update ---
    model_config = ConfigDict(
        json_schema_extra = {
            "example": {
                "response_text": "That's a bit lower than we were expecting. Based on the market, I can meet you at $48,000. How does that sound?"
            }
        }
    )