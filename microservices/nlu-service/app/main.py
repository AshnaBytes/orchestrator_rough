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
    sentiment: str


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
    # 3️⃣ Sentiment Detection
    # -------------------------
    def detect_sentiment(text: str) -> str:
        text = text.lower()
        negative_words = ["high", "disappointed","expensive", "unfair", "bad", "angry", "upset", "worst", "frustrated", "annoyed"]
        positive_words = ["good", "great", "happy", "perfect", "amazing", "love"]

        if any(w in text for w in negative_words):
            return "negative"
        if any(w in text for w in positive_words):
            return "positive"
        else:
            return "neutral"

    sentiment = detect_sentiment(text)

    return {
        "intent": intent,
        "entities": {"PRICE": price},
        "sentiment": sentiment,
    }
