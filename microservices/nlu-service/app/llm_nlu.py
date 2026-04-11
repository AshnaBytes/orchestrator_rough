"""
LLM-Based NLU Parser using LangChain + Groq.

Uses ChatGroq with structured output (Pydantic) for type-safe,
deterministic NLU extraction. LangChain handles prompt templating,
output parsing, and retries automatically.

Model: llama-3.1-8b-instant (fastest, cheapest Groq model)
Temperature: 0.0 (fully deterministic)
"""

import logging
from typing import Optional, Literal

from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Structured Output Schema — LangChain forces the LLM to match this exactly
# ---------------------------------------------------------------------------
class NLUParsed(BaseModel):
    """Structured NLU output that LangChain will enforce via tool calling."""

    intent: Literal[
        "GREET", "BYE", "MAKE_OFFER", "DEAL",
        "ASK_QUESTION", "ASK_PREVIOUS_OFFER", "UNKNOWN"
    ] = Field(description="The user's intent classification")

    price: Optional[float] = Field(
        default=None,
        description="The price the user is offering. Only set if intent is MAKE_OFFER, otherwise null."
    )

    sentiment: Literal["positive", "neutral", "negative"] = Field(
        default="neutral",
        description="The user's emotional sentiment"
    )


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a precise NLU parser for a price negotiation chatbot.
Classify the user's message and extract structured data.

Intent classification rules:
- GREET: user is greeting (hi, hello, hey, good morning, etc.)
- BYE: user is saying goodbye (bye, see you, later, goodbye, etc.)
- MAKE_OFFER: user is explicitly proposing a specific price (e.g. "I'll give you 150", "how about $200", "my offer is 180 bucks", "a hundred and fifty")
- DEAL: user is accepting/agreeing to a price (deal, accepted, agreed, I agree, let's do it, etc.)
- ASK_PREVIOUS_OFFER: user is asking about a previous/earlier offer or counter
- ASK_QUESTION: user is asking any other question about the product
- UNKNOWN: anything else that doesn't fit

Price extraction rules:
- ONLY set price when intent is MAKE_OFFER
- Handle natural language: "a hundred and fifty" → 150.0, "1.5k" → 1500.0
- If NO price offer is being made, price MUST be null

Sentiment rules:
- positive: user seems happy, enthusiastic, or satisfied
- negative: user seems frustrated, angry, or dissatisfied
- neutral: everything else"""


# ---------------------------------------------------------------------------
# Prompt Template
# ---------------------------------------------------------------------------
prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "User message: {text}"),
])


# ---------------------------------------------------------------------------
# Build the chain (called once at startup)
# ---------------------------------------------------------------------------
def build_nlu_chain(groq_api_key: str):
    """
    Build a LangChain chain that:
    1. Formats the user message into the prompt
    2. Calls Groq's llama3-8b-8192
    3. Forces structured output via with_structured_output(NLUParsed)
    4. Returns a validated NLUParsed Pydantic object

    This is the "structured output" pattern — LangChain uses tool calling
    under the hood to guarantee the LLM returns exactly the fields we need.
    """
    llm = ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0.0,
        max_tokens=150,
        api_key=groq_api_key,
    )

    # with_structured_output forces the LLM output to match our Pydantic model
    structured_llm = llm.with_structured_output(NLUParsed)

    # chain: prompt → structured LLM → NLUParsed object
    chain = prompt | structured_llm

    return chain


async def parse(text: str, chain) -> dict:
    """
    Run the NLU chain on the user's text.

    Returns:
        dict with keys: intent (str), price (float|None), sentiment (str)

    Raises:
        Exception on any LangChain/Groq failure → caller uses regex fallback.
    """
    logger.info("[LLM NLU] Parsing: %r", text)

    result: NLUParsed = await chain.ainvoke({"text": text})

    logger.info("[LLM NLU] Parsed: intent=%s, price=%s, sentiment=%s",
                result.intent, result.price, result.sentiment)

    return {
        "intent": result.intent,
        "price": result.price,
        "sentiment": result.sentiment,
    }
