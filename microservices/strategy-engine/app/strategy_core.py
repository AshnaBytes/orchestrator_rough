# Purpose: Houses the core business logic for the negotiation strategy.
# (Upgraded to v1.2.2 - Explicit Offer Counting)

from .schemas import StrategyInput, StrategyOutput
import logging
import math

# Set up a logger for this module
logger = logging.getLogger(__name__)

# --- Policy Configuration ---
POLICY_VERSION = "1.3.3"

# Thresholds
LOWBALL_THRESHOLD_PERCENT = 0.70
SENTIMENT_ACCEPT_THRESHOLD_PERCENT = 0.95 

# New: Offer Count Threshold
# We trigger "Final Offer" logic if the user has made at least this many offers
# (including the current one).
USER_OFFER_THRESHOLD = 4 

# --- NEW CONCESSION FACTORS (Tougher Logic) ---
# Standard: Only drop 25% of the gap (was 50%)
STANDARD_CONCESSION_FACTOR = 0.25 

# Final: Meet halfway (was 75%)
FINAL_CONCESSION_FACTOR = 0.50 
# ----------------------------------------------

def get_last_bot_offer(input_data: StrategyInput) -> float:
    """
    Helper function to find the most recent price offered by the Bot.
    """
    for turn in reversed(input_data.history):
        role = turn.get("role", "").lower()
        if role == "assistant" or role == "bot":
            if "counter_price" in turn and turn["counter_price"] is not None:
                return float(turn["counter_price"])
            if "offer" in turn and turn["offer"] is not None:
                return float(turn["offer"])
    return input_data.asking_price

def count_user_offers(history: list) -> int:
    """
    Counts how many times the user has made a move in the history.
    """
    count = 0
    for turn in history:
        if turn.get("role", "").lower() == "user":
            count += 1
    return count

def make_decision(input_data: StrategyInput) -> StrategyOutput:
    
    logger.info(f"Processing decision for session: {input_data.session_id}")

        # NEW: Handle Greeting, Bye, Deal, and Previous Offer
    last_user_offer = None
    last_bot_offer = None

    # Find last offers from history
    for turn in reversed(input_data.history):
        role = turn.get("role", "").lower()
        if not last_bot_offer and role in ("bot", "assistant"):
            if "counter_price" in turn and turn["counter_price"] is not None:
                last_bot_offer = turn["counter_price"]
        if not last_user_offer and role == "user":
            if "offer" in turn and turn["offer"] is not None:
                last_user_offer = turn["offer"]

    # =================================================================
    # RULE 0: Over-Asking-Price Guard
    # If the user offers MORE than the asking price, politely inform
    # them and redirect. We do not want to take more than listed.
    # =================================================================
    if input_data.user_intent == "MAKE_OFFER" and input_data.user_offer > input_data.asking_price:
        return StrategyOutput(
            action="REJECT",
            response_key="OFFER_ABOVE_ASKING",
            counter_price=input_data.asking_price,
            policy_type="rule-based",
            policy_version=POLICY_VERSION,
            decision_metadata={"asking_price": input_data.asking_price}
        )

    # Handle GREET
    if input_data.user_intent == "GREET":
        return StrategyOutput(
            action="REJECT",
            response_key="GREET_HELLO",
            counter_price=None,
            policy_type="rule-based",
            policy_version=POLICY_VERSION,
            decision_metadata={}
        )

    # Handle BYE
    if input_data.user_intent == "BYE":
        return StrategyOutput(
            action="REJECT",
            response_key="BYE_GOODBYE",
            counter_price=None,
            policy_type="rule-based",
            policy_version=POLICY_VERSION,
            decision_metadata={}
        )

    # Handle DEAL confirmation
    if input_data.user_intent == "DEAL":
        return StrategyOutput(
            action="ACCEPT",
            response_key="DEAL_ACCEPTED",
            counter_price=last_bot_offer or input_data.user_offer,
            policy_type="rule-based",
            policy_version=POLICY_VERSION,
            decision_metadata={"rule": "deal_confirmed"}
        )

    # Handle previous offer query
    if input_data.user_intent == "ASK_PREVIOUS_OFFER":
        return StrategyOutput(
            action="REJECT",
            response_key="PREVIOUS_OFFER",
            counter_price=None,
            policy_type="rule-based",
            policy_version=POLICY_VERSION,
            decision_metadata={
                "user_offer": last_user_offer,
                "bot_offer": last_bot_offer
            }
        )

    # =================================================================
    # RULE 1 & 2 (Accept Rules) - UNCHANGED
    # =================================================================
    sentiment_accept_threshold = input_data.mam * SENTIMENT_ACCEPT_THRESHOLD_PERCENT
    if (input_data.user_sentiment == 'negative' and 
        input_data.user_offer >= sentiment_accept_threshold):
        return StrategyOutput(action="ACCEPT", response_key="ACCEPT_SENTIMENT_CLOSE", counter_price=input_data.user_offer, policy_type="rule-based", policy_version=POLICY_VERSION, decision_metadata={"rule": "sentiment_accept"})

    if input_data.user_offer >= input_data.mam:
        return StrategyOutput(action="ACCEPT", response_key="ACCEPT_FINAL", counter_price=input_data.user_offer, policy_type="rule-based", policy_version=POLICY_VERSION, decision_metadata={"rule": "standard_accept"})
    
    # =================================================================
    # RULE 3: Lowball REJECT Logic - UNCHANGED
    # =================================================================
    lowball_threshold = input_data.mam * LOWBALL_THRESHOLD_PERCENT
    if input_data.user_offer < lowball_threshold:
        return StrategyOutput(action="REJECT", response_key="REJECT_LOWBALL", counter_price=None, policy_type="rule-based", policy_version=POLICY_VERSION, decision_metadata={"rule": "lowball_reject"})

    # =================================================================
    # RULE 4: Counter-Offer Logic (Offer-Count Aware)
    # =================================================================
    
    # 1. Determine our current standing
    current_bot_price = get_last_bot_offer(input_data)
    
    # 2. Count Offers
    # We count history offers + 1 (the current offer being processed)
    past_user_offers = count_user_offers(input_data.history)
    total_user_offers = past_user_offers + 1
    
    logger.info(f"User Offer Count: {total_user_offers} (Threshold: {USER_OFFER_THRESHOLD})")

    # 3. Decide Strategy based on Count
    if total_user_offers > USER_OFFER_THRESHOLD:
        # --- FINAL ROUND STRATEGY ---
        concession_factor = FINAL_CONCESSION_FACTOR
        response_key = "COUNTER_FINAL_OFFER"
        logger.info("Offer Threshold reached. Triggering Final Offer.")
    else:
        # --- STANDARD STRATEGY ---
        concession_factor = STANDARD_CONCESSION_FACTOR
        response_key = "STANDARD_COUNTER"

    # 4. Calculate Concession
    gap = current_bot_price - input_data.user_offer
    drop_amount = gap * concession_factor
    midpoint = current_bot_price - drop_amount

#gpt suggested method for bot not going above its previous offer
    final_counter = min(current_bot_price, max(input_data.mam, midpoint))
    final_counter = math.ceil(final_counter)
    


    return StrategyOutput(
        action="COUNTER",
        response_key=response_key,
        counter_price=final_counter,
        policy_type="rule-based",
        policy_version=POLICY_VERSION,
        decision_metadata={
            "rule": "offer_count_aware_counter",
            "mam": input_data.mam,
            "offer_number": total_user_offers,
            "is_final_round": total_user_offers >= USER_OFFER_THRESHOLD,
            "final_counter": final_counter
        }
    )