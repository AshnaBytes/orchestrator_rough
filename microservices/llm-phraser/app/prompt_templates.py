# Purpose: Manages and formats all prompt templates for the LLM.
# (Upgraded to v1.2 - Full Contextual Support)

from .schemas import PhraserInput
import logging
from typing import Tuple

logger = logging.getLogger(__name__)
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
    "5. Be concise and crisp. Do not add unnecessary 'fluff', overly excited "
    "   sales pitches, or long-winded friendly padding. Get straight to the point.\n"
    "6. CRITICAL MULTILINGUAL RULE: The user's language has been detected as '{language}'. "
    "   You MUST write your entire response in that language. "
    "   (roman_urdu = Urdu written in Latin letters, urdu = Urdu script, english = English, other = match the detected language)"
)

# --- Prompt Templates ---
TEMPLATES = {
    "GREET_HELLO": [
        "Template: Hi there! How can I help you today?",
        "Template: Hello! Ready to negotiate?",
        "Template: Hey! Good to see you.",
    ],
    "BYE_GOODBYE": [
        "Template: Goodbye! Hope we can make a deal soon.",
        "Template: Bye! Take care.",
        "Template: See you later! Thanks for the chat.",
    ],
    "DEAL_ACCEPTED": [
        "Template: Great! I'm glad we agreed on this.",
        "Template: Awesome, the deal is confirmed.",
        "Template: Fantastic! We have a deal.",
    ],
    "PREVIOUS_OFFER": [
        "Template: Earlier you offered {user_offer}, and I countered with {bot_offer}.",
        "Template: You last offered {user_offer}, and my response was {bot_offer}.",
    ],
    "OUT_OF_SCOPE_QUESTION": [
        "Template: I am an automated bargaining agent here to negotiate the price. For product details or general questions, please check the main product description.",
        "Template: My sole purpose is to negotiate the best price with you. I cannot answer general questions, but I'm ready for your offer!",
        "Template: I'm here exclusively for price bargaining. Please make an offer or ask me about the price, as I am not equipped to answer other questions.",
    ],
    "OFFER_ABOVE_ASKING": [
        "Template: That's very generous! However, our listed asking price is {price} — we wouldn't want you to overpay. Would you like to offer at or below that?",
        "Template: I appreciate it, but you've actually offered more than our asking price of {price}. You don't need to pay that much! Feel free to negotiate below {price}.",
        "Template: Wow, thank you! But our asking price is only {price} — we can't take more than that. Make an offer at or below {price} and we can talk!",
    ],
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
    # 4a. Hold Firm Counter-Offer (User is stalling)
    # Tone: Completely normal counter-offer (the price math handles the 'firmness', not the text)
    "COUNTER_HOLD_FIRM": [
        "Template: How about we agree on {price}?",
        "Template: I can offer this to you for {price}.",
        "Template: Let's make it {price}. How does that sound?",
    ],
    # 4b. Encourage Close Counter-Offer (User made a big jump)
    "COUNTER_ENCOURAGE_CLOSE": [
        "Template: I see you're serious about making a deal. Let's make this happen—how about {price}?",
        "Template: You've made a great move. If we can just meet at {price}, we have a deal right now.",
        "Template: We are very close to an agreement! Let's meet at {price} and wrap this up.",
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
    ],
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

    # Format template (handle PREVIOUS_OFFER with metadata)
    try:
        if key == "PREVIOUS_OFFER":
            user_offer = input_data.decision_metadata.get("user_offer", "N/A")
            bot_offer = input_data.decision_metadata.get("bot_offer", "N/A")
            formatted_prompt = selected_template.format(
                user_offer=user_offer, bot_offer=bot_offer
            )
        else:
            price_str = f"Rs {price:,.0f}" if price is not None else ""
            formatted_prompt = selected_template.format(price=price_str)
    except Exception as e:
        logger.exception("Error formatting prompt: %s", e)
        formatted_prompt = "Template: I'm not sure how to respond."

    # Inject detected language into System Prompt
    formatted_system_prompt = SYSTEM_PROMPT.format(
        language=input_data.language or "english"
    )

    return formatted_system_prompt, formatted_prompt
