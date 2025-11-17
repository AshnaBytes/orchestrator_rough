import re
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="NLU Service (MS2)")


class NLUInput(BaseModel):
    text: str
    session_id: str


class NLUOutput(BaseModel):
    intent: str
    entities: dict
    sentiment: str  # hard-coded to "neutral"


@app.post("/parse", response_model=NLUOutput)
async def parse(input: NLUInput):
    text = input.text.lower()

    # -------------------------
    # 1️⃣ PRICE Extraction
    # -------------------------
    price_match = re.search(r"(\d+)", text)
    price = float(price_match.group(1)) if price_match else None

    # -------------------------
    # 2️⃣ Intent Detection
    # -------------------------
    if price:
        intent = "propose_offer"
    else:
        intent = "ask_question"

    # -------------------------
    # 3️⃣ Sentiment (placeholder)
    # -------------------------
    sentiment = "neutral"

    return {
        "intent": intent,
        "entities": {"PRICE": price},
        "sentiment": sentiment,
    }
