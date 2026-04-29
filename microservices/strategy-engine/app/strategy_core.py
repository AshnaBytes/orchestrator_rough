# negotiation_engine_v2.py
# Strategy Version: 2.0.0 — Psychological + Pattern-Aware

from .schemas import StrategyInput, StrategyOutput
import logging
import math

logger = logging.getLogger(__name__)

POLICY_VERSION = "2.0.0"

# --- Thresholds ---
LOWBALL_THRESHOLD_PERCENT = 0.70
MAM_ACCEPT_THRESHOLD = 1.00  # Accept at or above MAM
SENTIMENT_ACCEPT_THRESHOLD = 0.95  # Accept slightly below MAM if user is frustrated

# --- Concession Ladder (Diminishing Returns) ---
# Each entry is (min_offer_number, concession_factor)
# As offers increase, the bot gives less and less away each round.
CONCESSION_LADDER = [
    (1, 0.35),  # Offer 1–2: Give 35% of the gap (generous opening)
    (3, 0.20),  # Offer 3–4: Give 20% of the gap (slowing down)
    (5, 0.10),  # Offer 5+:  Give only 10% (near-final resistance)
]
FINAL_OFFER_FACTOR = 0.50  # When triggering FINAL, split remaining gap

# --- Pattern Detection ---
STALL_DELTA_PERCENT = 0.01  # If user's offer moves <1% of asking price = stalling
RAPID_CLOSE_PERCENT = 0.15  # If user jumps >15% of gap in one move = serious buyer

# --- Offer Count ---
FINAL_OFFER_THRESHOLD = 5


# ── Helpers ──────────────────────────────────────────────────────────────────


def _get_role(turn: dict) -> str:
    """
    Normalize the speaker field.
    Orchestrator writes:  {"from": "user"}  / {"from": "ina"}
    Older turns may use: {"role": "user"}  / {"role": "assistant" | "bot"}
    Returns a lowercase canonical role: 'user', 'bot', or ''.
    """
    raw = turn.get("role") or turn.get("from") or ""
    raw = raw.lower()
    if raw in ("assistant", "ina", "bot"):
        return "bot"
    return raw  # 'user' or ''


def get_last_bot_offer(input_data: StrategyInput) -> float:
    for turn in reversed(input_data.history):
        if _get_role(turn) == "bot":
            for key in ("bot_offer", "counter_price", "offer"):
                if turn.get(key) is not None:
                    return float(turn[key])
    return input_data.asking_price


def get_concession_factor(offer_number: int) -> float:
    """Returns a diminishing concession factor based on offer number."""
    factor = CONCESSION_LADDER[0][1]
    for min_offer, f in CONCESSION_LADDER:
        if offer_number >= min_offer:
            factor = f
    return factor


def count_user_offers(history: list) -> int:
    return sum(1 for t in history if _get_role(t) == "user")


def get_user_offer_history(history: list) -> list[float]:
    """Returns all user offer prices in chronological order."""
    return [
        float(t.get("user_offer") or t.get("offer"))
        for t in history
        if _get_role(t) == "user"
        and (t.get("user_offer") is not None or t.get("offer") is not None)
    ]


def detect_pattern(
    user_offer: float, offer_history: list[float], asking_price: float
) -> str:
    """
    Detects negotiation patterns:
    - 'stalling': user barely moving
    - 'rapid_close': user jumped a large amount
    - 'normal': standard progression
    """
    if not offer_history:
        return "normal"

    last_offer = offer_history[-1]
    delta = user_offer - last_offer

    stall_threshold = asking_price * STALL_DELTA_PERCENT
    if delta < stall_threshold:
        return "stalling"

    if offer_history:
        # Calculate how much of the remaining gap the user just closed
        old_gap = asking_price - last_offer  # rough proxy
        if old_gap > 0 and (delta / old_gap) > RAPID_CLOSE_PERCENT:
            return "rapid_close"

    return "normal"


# ── Main Decision Function ────────────────────────────────────────────────────


def make_decision(input_data: StrategyInput) -> StrategyOutput:
    logger.info(f"[v2.0] Processing session: {input_data.session_id}")

    # ── Extract context from history ─────────────────────────────────────────
    last_user_offer = None
    last_bot_offer = None
    for turn in reversed(input_data.history):
        role = _get_role(turn)
        if not last_bot_offer and role == "bot":
            last_bot_offer = (
                turn.get("bot_offer") or turn.get("counter_price") or turn.get("offer")
            )
        if not last_user_offer and role == "user":
            last_user_offer = turn.get("user_offer") or turn.get("offer")

    # ── Guard: Over-asking price ──────────────────────────────────────────────
    if (
        input_data.user_intent == "MAKE_OFFER"
        and input_data.user_offer > input_data.asking_price
    ):
        return StrategyOutput(
            action="REJECT",
            response_key="OFFER_ABOVE_ASKING",
            counter_price=input_data.asking_price,
            policy_type="rule-based",
            policy_version=POLICY_VERSION,
            decision_metadata={"asking_price": input_data.asking_price},
        )

    # ── RULE 1: Accept at or above MAM ───────────────────────────────────────
    if input_data.user_offer >= input_data.mam:
        return StrategyOutput(
            action="ACCEPT",
            response_key="ACCEPT_FINAL",
            counter_price=input_data.user_offer,
            policy_type="rule-based",
            policy_version=POLICY_VERSION,
            decision_metadata={"rule": "standard_accept"},
        )

    # ── RULE 2: Sentiment-adjusted accept (frustrated buyer near MAM) ─────────
    # Only trigger if negative AND user has been negotiating for a while
    past_offers = count_user_offers(input_data.history)
    if (
        input_data.user_sentiment == "negative"
        and past_offers >= 2
        and input_data.user_offer >= input_data.mam * SENTIMENT_ACCEPT_THRESHOLD
    ):
        return StrategyOutput(
            action="ACCEPT",
            response_key="ACCEPT_SENTIMENT_CLOSE",
            counter_price=input_data.user_offer,
            policy_type="rule-based",
            policy_version=POLICY_VERSION,
            decision_metadata={"rule": "sentiment_accept"},
        )

    # ── RULE 3: Lowball rejection ─────────────────────────────────────────────
    if input_data.user_offer < input_data.mam * 0.70:
        return StrategyOutput(
            action="REJECT",
            response_key="REJECT_LOWBALL",
            counter_price=None,
            policy_type="rule-based",
            policy_version=POLICY_VERSION,
            decision_metadata={"rule": "lowball_reject"},
        )

    # ── RULE 4: Counter-offer (pattern + psychology aware) ───────────────────
    current_bot_price = get_last_bot_offer(input_data)
    total_offers = past_offers + 1  # includes current one
    offer_history = get_user_offer_history(input_data.history)
    pattern = detect_pattern(
        input_data.user_offer, offer_history, input_data.asking_price
    )

    logger.info(
        f"Offer #{total_offers} | Pattern: {pattern} | Sentiment: {input_data.user_sentiment}"
    )

    # ── Determine concession factor ───────────────────────────────────────────
    is_final_round = total_offers >= FINAL_OFFER_THRESHOLD

    if is_final_round:
        concession_factor = FINAL_OFFER_FACTOR
        response_key = "COUNTER_FINAL_OFFER"

    else:
        concession_factor = get_concession_factor(total_offers)

        # Pattern modifiers
        if pattern == "stalling":
            # User barely moved → bot barely moves too (hold firm)
            concession_factor *= 0.40
            response_key = "COUNTER_HOLD_FIRM"

        elif pattern == "rapid_close":
            # User is serious, closing fast → slight extra generosity to seal deal
            concession_factor *= 1.30
            response_key = "COUNTER_ENCOURAGE_CLOSE"

        else:
            response_key = "STANDARD_COUNTER"

        # Sentiment modifier: enthusiastic users get less concession
        if input_data.user_sentiment == "positive":
            concession_factor *= 0.80  # They're excited — no need to over-discount

    # ── Calculate final counter price ─────────────────────────────────────────
    gap = current_bot_price - input_data.user_offer
    drop = gap * concession_factor
    midpoint = current_bot_price - drop

    # Never go below MAM, never exceed previous bot price
    final_counter = math.ceil(min(current_bot_price, max(input_data.mam, midpoint)))

    return StrategyOutput(
        action="COUNTER",
        response_key=response_key,
        counter_price=final_counter,
        policy_type="rule-based",
        policy_version=POLICY_VERSION,
        decision_metadata={
            "rule": "pattern_aware_diminishing_counter",
            "mam": input_data.mam,
            "offer_number": total_offers,
            "pattern": pattern,
            "sentiment": input_data.user_sentiment,
            "is_final_round": is_final_round,
            "concession_factor_used": round(concession_factor, 3),
            "final_counter": final_counter,
        },
    )
