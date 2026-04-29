from pydantic import BaseModel
from typing import Optional


class NLUInput(BaseModel):
    text: str
    session_id: str


class NLUOutput(BaseModel):
    intent: str
    entities: dict
    sentiment: str
    language: str  # e.g. "english", "roman_urdu", "urdu", "other"
    error_message: Optional[str] = None
