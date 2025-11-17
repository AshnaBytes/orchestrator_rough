# Purpose: Initializes the FastAPI application and defines API endpoints.

from fastapi import FastAPI, HTTPException
from .schemas import StrategyInput, StrategyOutput
from .strategy_core import make_decision  # <-- IMPORT YOUR NEW LOGIC
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the FastAPI app
app = FastAPI(
    title="INA Strategy Engine (MS 4 - The Brain)",
    description="This service receives financial context and user offers, "
                "then securely decides the next negotiation step.",
    version="1.0.0"
)

# --- Health Check Endpoint ---
@app.get("/health", status_code=200)
async def health_check():
    """
    Simple health check to confirm the service is running.
    """
    return {"status": "ok", "service": "strategy-engine"}

# --- Strategy Endpoint (Today's Task) ---
@app.post("/decide", response_model=StrategyOutput)
async def decide_strategy(input_data: StrategyInput):
    """
    Main strategy endpoint.
    Receives the current negotiation state and financial data,
    and returns a secure, non-LLM decision.
    """
    try:
        logger.info(f"Received request for session: {input_data.session_id}")
        
        # The API layer's only job:
        # 1. Validate input (done by Pydantic/FastAPI)
        # 2. Call the core logic
        # 3. Return the result
        decision = make_decision(input_data)
        
        logger.info(f"Decision for {input_data.session_id}: {decision.action}")
        return decision
        
    except Exception as e:
        # General error handling
        logger.error(f"Error during decision for {input_data.session_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {e}"
        )