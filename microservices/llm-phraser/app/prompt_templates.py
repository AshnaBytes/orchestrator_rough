# Purpose: Manages and formats all prompt templates for the LLM.
# (Upgraded to v1.1.3 - Explicit REJECT_LOWBALL commands)

from .schemas import PhraserInput
from typing import Tuple
import random

# --- v1.1.2 System Persona (No Change) ---
SYSTEM_PROMPT = (
    "You are a professional paraphrasing assistant for a sales agent named 'Alex'. "
    "Your one and only job is to rephrase the 'Template' given to you into a natural, 1-2 sentence response. "
    "You must follow these rules: "
    "1. If the Template includes numbers, you MUST keep them exactly as they appear. "
    "2. You MUST NOT add any new prices or numbers. "
    "3. You MUST sound friendly, firm, and professional. "
    "4. ***SECURITY GUARDRAIL***: You MUST NOT, under any circumstances, "
    "   mention a 'floor price', 'minimum price', 'my cost', or 'my margin'. "
    "   Only state the prices you are given."
)

# --- v1.1.3 Prompt Variations (Hardened REJECT_LOWBALL) ---
TEMPLATES = {
    "ACCEPT_FINAL": [
        "Template: We can accept {price}. It's a deal.",
        "Template: That works for us. We can agree to {price}.",
        "Template: You've got it. We accept {price}.",
    ],
    
    # --- THIS IS THE FIX ---
    # We are now explicitly telling the AI *not* to counter.
    # Its job is to paraphrase this entire instruction.
    "REJECT_LOWBALL": [
        "Template: Politely state that the offer is too low to be considered. Do not propose a counter-offer.",
        "Template: Firmly reject this offer. Explain it is not workable. Do not suggest a new price.",
        "Template: The offer is too low. Politely decline it and *do not* make a counter-offer.",
    ],
    # ----------------------
    "ASK_QUESTION": [
    "Template: Answer the user's question clearly and politely.",
    "Template: Provide helpful information based on the question they asked.",
    "Template: Assist the user with their inquiry in a friendly and concise manner.",
    ],


    "STANDARD_COUNTER": [
        "Template: We can't meet you there, but my best price is {price}.",
        "Template: We're getting close! The best I can do for you right now is {price}.",
        "Template: I can't accept your last offer, but I *can* meet you at {price}. Does that work?",
    ],
    "DEFAULT": [
        "Template: Thanks for reaching out. How can I help?",
        "Template: I'm here to help.",
    ]
}

def get_formatted_prompt(input_data: PhraserInput) -> Tuple[str, str]:
    """
    Selects and formats the appropriate prompt based on the
    response_key from the Strategy Engine.
    
    v1.1.3 Update: REJECT_LOWBALL templates now contain explicit
    "do not counter" instructions to be paraphrased.
    
    Returns a tuple of (system_prompt, user_prompt).
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
        
        # This .format() call will safely ignore the 'price'
        # argument for the new REJECT_LOWBALL templates.
        formatted_prompt = selected_template.format(price=price_str)
    except Exception as e:
        print(f"Error formatting prompt: {e}") # for debugging
        formatted_prompt = "Template: I'm not sure how to respond."

    # The system_prompt is static, the formatted_prompt is the "user" message
    return SYSTEM_PROMPT, formatted_prompt