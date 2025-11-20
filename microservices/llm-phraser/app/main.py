# Purpose: Initializes the FastAPI application and defines API endpoints.

from fastapi import FastAPI, HTTPException, Depends
from .schemas import PhraserInput, PhraserOutput
from .llm_client import generate_llm_response  # <-- IMPORT THE NEW FUNCTION

import os
import logging
from groq import AsyncGroq
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# --- Load environment variables from .env file ---
load_dotenv()

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- API Key and Client Management ---
API_KEY = os.environ.get("GROQ_API_KEY")

if not API_KEY:
    logger.error("FATAL: GROQ_API_KEY environment variable not set.")
    # In a real app, you might raise an exception to stop it from starting
    # raise ValueError("GROQ_API_KEY environment variable not set.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the client when the app starts
    app.state.groq_client = AsyncGroq(api_key=API_KEY)
    logger.info("Groq client initialized.")
    yield
    # (No shutdown needed, but you could add cleanup here)
    logger.info("Shutting down...")

app = FastAPI(
    title="INA LLM Phraser (MS 5 - The Mouth)",
    description="This service receives a *command* (not secrets) "
                "and phrases it persuasively using an LLM.",
    version="1.0.0",
    lifespan=lifespan # Attach the lifespan event handler
)

# --- Dependency to get the client ---
async def get_groq_client():
    if not app.state.groq_client:
        raise HTTPException(status_code=503, detail="Groq client is not available.")
    return app.state.groq_client

# --- Health Check Endpoint ---
@app.get("/health", status_code=200)
async def health_check():
    return {"status": "ok", "service": "llm-phraser"}

# --- LLM Phrasing Endpoint (Now Refactored) ---
@app.post("/phrase", response_model=PhraserOutput)
async def generate_phrase(
    input_data: PhraserInput,
    client: AsyncGroq = Depends(get_groq_client) # Inject the client
):
    """
    Receives a command from the Strategy Engine (MS 4) and
    generates a persuasive, natural language response.
    """
    
    # 1. Call the isolated logic from our client file
    #    main.py doesn't know *how* the text is made, only who to ask.
    try:
        response_text = await generate_llm_response(input_data, client)
        
        # 2. Return the response
        return PhraserOutput(response_text=response_text)

    except Exception as e:
        # This is now a "catch-all" for unexpected errors
        logger.error(f"Unhandled error in /phrase endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal server error occurred.")