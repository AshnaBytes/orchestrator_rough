# Purpose: Initializes the FastAPI application and defines API endpoints.

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from .schemas import PhraserInput, PhraserOutput
from prometheus_fastapi_instrumentator import Instrumentator
from dotenv import load_dotenv

# --- Load environment variables from .env file ---
load_dotenv()

from .llm_client import generate_llm_response

from groq import AsyncGroq

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------- Internal Service Key ----------------------
INTERNAL_KEY = os.getenv("INTERNAL_SERVICE_KEY", "")

# --- API Key and Client Management ---
API_KEY = os.environ.get("GROQ_API_KEY")

if not API_KEY:
    logger.error("FATAL: GROQ_API_KEY environment variable not set.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the client when the app starts
    app.state.groq_client = AsyncGroq(api_key=API_KEY)
    logger.info("Groq client initialized.")
    yield
    logger.info("Shutting down...")

app = FastAPI(
    title="INA LLM Phraser (MS 5 - The Mouth)",
    description="This service receives a *command* (not secrets) "
                "and phrases it persuasively using an LLM.",
    version="1.0.0",
    lifespan=lifespan
)

# Prometheus Instrumentation
Instrumentator().instrument(app).expose(app)


# ---------------------- Auth Middleware ----------------------
@app.middleware("http")
async def verify_internal_key(request: Request, call_next):
    """
    Verify that incoming requests carry the correct X-Internal-Key header.
    Health check endpoint is exempt so Docker/k8s healthchecks still work.
    """
    if request.url.path in ("/health", "/", "/docs", "/openapi.json"):
        return await call_next(request)

    incoming_key = request.headers.get("X-Internal-Key", "")
    if not INTERNAL_KEY or incoming_key != INTERNAL_KEY:
        logger.warning(f"Unauthorized request to {request.url.path} — key mismatch")
        return JSONResponse(
            status_code=403,
            content={"detail": "Forbidden: Invalid internal service key."},
        )

    return await call_next(request)


# --- Dependency to get the client ---
async def get_groq_client():
    if not app.state.groq_client:
        raise HTTPException(status_code=503, detail="Groq client is not available.")
    return app.state.groq_client

# --- Health Check Endpoint ---
@app.get("/health", status_code=200)
async def health_check():
    return {"status": "ok", "service": "llm-phraser"}

# --- LLM Phrasing Endpoint ---
@app.post("/api/v1/phrase", response_model=PhraserOutput)
async def generate_phrase(
    input_data: PhraserInput,
    client: AsyncGroq = Depends(get_groq_client)
):
    """
    Receives a command from the Strategy Engine (MS 4) and
    generates a persuasive, natural language response.
    """
    
    try:
        response_text = await generate_llm_response(input_data, client)
        return PhraserOutput(response_text=response_text)

    except Exception as e:
        logger.error(f"Unhandled error in /phrase endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal server error occurred.")