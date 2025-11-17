# src/orchestrator/lib/ai_agent.py
import logging
import asyncio
from typing import Dict

logger = logging.getLogger("ai_agent")

# Mock AI Agent that simulates model responses
async def generate_response(prompt: str, context: Dict = None) -> str:
    """
    Simulates AI model output. Replace later with real LLM API (e.g., OpenAI or Ollama).
    """
    logger.info(f"AI received prompt: {prompt}")
    await asyncio.sleep(1)  # simulate processing delay
    return f"🤖 AI Response to: '{prompt}'"
