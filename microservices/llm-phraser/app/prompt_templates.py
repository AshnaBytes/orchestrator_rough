# Purpose: Manages and formats all prompt templates for the LLM.
# (Upgraded to v1.2 - Full Contextual Support)

from .schemas import PhraserInput
from typing import Tuple
import random

# --- System Persona (Paraphrasing Assistant) ---
SYSTEM_PROMPT = (
    "You are a professional paraphrasing assistant for a sales agent named 'Alex'. "
    "Your one and only job is to rephrase the 'Template' given to you into a natural, 1-2 sentence response. "
    "You must follow these rules: "
    "1. You MUST use all prices and numbers from the Template exactly as they are. "
    "2. You MUST NOT add any new prices or numbers. "
    "3. You MUST sound friendly, firm, and professional. "
    "4. ***SECURITY GUARDRAIL***: You MUST NOT, under any circumstances, "
    "   mention a 'floor price', 'minimum price', 'my cost', or 'my margin'. "
    "   Only state the prices you are given."
)

# --- Prompt Templates ---
TEMPLATES = {
    # 1. Standard Acceptance
    "ACCEPT_FINAL": [
        "Template: We can accept {price}. It's a deal.",
        "Template: That works for us. We can agree to {price}.",
        "Template: You've got it. We accept {price}.",
    ],

    # 2. Sentiment/Panic Acceptance (New for v1.3 Brain)
    # Tone: Reluctant, conciliatory, "doing you a favor".
    "ACCEPT_SENTIMENT_CLOSE": [
        "Template: You know what, I want to make this work for you. We can accept {price}.",
        "Template: It's lower than I wanted, but I appreciate your business. Let's do {price}.",
        "Template: Since you've been patient, I can make an exception. We accept {price}.",
    ],
    
    # 3. Lowball Rejection
    "REJECT_LOWBALL": [
        "Template: Politely state that the offer is too low to be considered. Do not propose a counter-offer.",
        "Template: Firmly reject this offer. Explain it is not workable. Do not suggest a new price.",
        "Template: The offer is too low. Politely decline it and *do not* make a counter-offer.",
    ],

    # 4. Standard Counter-Offer
    "STANDARD_COUNTER": [
        "Template: We can't meet you there, but my best price is {price}.",
        "Template: We're getting close! The best I can do for you right now is {price}.",
        "Template: I can't accept your last offer, but I *can* meet you at {price}. Does that work?",
    ],

    # 5. Final Offer (New for v1.3 Brain)
    # Tone: Firm, conclusive, "take it or leave it".
    "COUNTER_FINAL_OFFER": [
        "Template: I've gone as low as I can. {price} is my absolute final offer.",
        "Template: I can't go any lower than this. {price} is the final price.",
        "Template: This is the best I can do. {price}, take it or leave it.",
    ],

    # Fallback
    "DEFAULT": [
        "Template: Thanks for reaching out. How can I help?",
        "Template: I'm here to help.",
    ]
}

def get_formatted_prompt(input_data: PhraserInput) -> Tuple[str, str]:
    """
    Selects and formats the appropriate prompt based on the
    response_key from the Strategy Engine.
    """
    
    key = input_data.response_key
    price = input_data.counter_price

    # 1. Get the list of prompt templates
    prompt_list = TEMPLATES.get(key, TEMPLATES["DEFAULT"])
    
    # 2. Select a random template
    selected_template = random.choice(prompt_list)
    
    # 3. Format the selected prompt
    try:
        price_str = f"${price:,.0f}" if price is not None else ""
        formatted_prompt = selected_template.format(price=price_str)
    except Exception as e:
        print(f"Error formatting prompt: {e}") 
        formatted_prompt = "Template: I'm not sure how to respond."

    return SYSTEM_PROMPT, formatted_prompt