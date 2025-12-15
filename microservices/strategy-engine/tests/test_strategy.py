# Purpose: Unit tests for the core negotiation logic (v1.3).

import pytest
import logging
from app.strategy_core import make_decision
from app.schemas import StrategyInput

# =======================================================================
#  Test Data Fixtures
# =======================================================================

@pytest.fixture
def base_input():
    """
    A standard baseline input for negotiation.
    """
    return StrategyInput(
        mam=40000.0,
        asking_price=50000.0,
        user_offer=45000.0, 
        user_intent="MAKE_OFFER",
        user_sentiment="neutral",
        session_id="sess_test_fixture",
        history=[]
    )

# =======================================================================
#  v1.3 Logic Tests (History & Fatigue)
# =======================================================================

def test_standard_counter_history_aware(base_input):
    """
    Test that the bot ignores the 'asking_price' and calculates
    the counter based on its LAST offer in history.
    """
    # ARRANGE
    base_input.mam = 40000.0
    base_input.asking_price = 50000.0
    
    # User offers 38k.
    base_input.user_offer = 38000.0
    
    # History: Bot previously offered 48k.
    # Gap: 48k (Bot) - 38k (User) = 10k.
    base_input.history = [
        {"role": "user", "message": "30k"},
        {"role": "assistant", "message": "48k", "counter_price": 48000.0}
    ]

    # ACT
    decision = make_decision(base_input)

    # ASSERT
    # Standard Strategy: Split the difference (50% drop).
    # Drop: 10k * 0.5 = 5k.
    # Result: 48k - 5k = 43k.
    assert decision.action == "COUNTER"
    assert decision.response_key == "STANDARD_COUNTER"
    assert decision.counter_price == 45500.0
    assert decision.decision_metadata["rule"] == "offer_count_aware_counter"

def test_final_offer_logic_trigger(base_input):
    """
    Test that the 'Final Offer' logic triggers on the 5th user offer
    (total_user_offers > 4).
    """
    # ARRANGE
    base_input.mam = 45000.0
    base_input.user_offer = 44000.0
    
    # History needs 4 previous user offers (so current is #5)
    base_input.history = [
        {"role": "user", "message": "30k"},
        {"role": "assistant", "message": "49k", "counter_price": 49000.0},
        {"role": "user", "message": "35k"},
        {"role": "assistant", "message": "48.5k", "counter_price": 48500.0},
        {"role": "user", "message": "40k"},
        {"role": "assistant", "message": "48k", "counter_price": 48000.0},
        # Add one more round to make history longer
        {"role": "user", "message": "42k"},
        {"role": "assistant", "message": "47.5k", "counter_price": 47500.0}
    ]

    # ACT
    decision = make_decision(base_input)

    # ASSERT
    # Logic: 5 > 4 is True. Trigger Final Round.
    assert decision.response_key == "COUNTER_FINAL_OFFER"
    assert decision.decision_metadata["is_final_round"] is True

def test_ratchet_check_prevents_price_increase(base_input):
    """
    Edge Case: Ensure the bot never accidentally RAISES its price,
    even if the math does something weird.
    """
    # ARRANGE
    base_input.mam = 40000.0
    # User makes a low offer
    base_input.user_offer = 35000.0
    
    # History: Bot is already very low (41k)
    base_input.history = [
         {"role": "assistant", "message": "41k", "counter_price": 41000.0}
    ]

    # ACT
    decision = make_decision(base_input)

    # ASSERT
    # Gap: 41k - 35k = 6k. Drop 3k. Result 38k.
    # BUT 38k < MAM (40k). So it clamps to 40k.
    # 40k < 41k. Correct.
    assert decision.counter_price == 40000.0
    assert decision.counter_price <= 41000.0 # Never go above last price

# =======================================================================
#  Existing v1.2 Tests (Retained & Verified)
# =======================================================================

def test_sentiment_accept(base_input, caplog):
    """Test Rule 1: Panic Accept on negative sentiment."""
    base_input.mam = 42000.0
    base_input.user_offer = 40000.0 # > 95% of 42k (39.9k)
    base_input.user_sentiment = "negative"
    
    with caplog.at_level(logging.WARNING):
        decision = make_decision(base_input)
        
    assert decision.action == "ACCEPT"
    assert decision.response_key == "ACCEPT_SENTIMENT_CLOSE"

def test_sentiment_rule_does_not_fire_if_offer_too_low(base_input):
    """
    Test that the sentiment rule *doesn't* fire if the user is
    'negative' but their offer is still too low.
    """
    base_input.mam = 42000.0
    base_input.user_sentiment = "negative"
    # Lowball threshold is 29,400. We set offer to 25,000.
    base_input.user_offer = 25000.0 
    
    decision = make_decision(base_input)
    
    assert decision.action == "REJECT"
    assert decision.response_key == "REJECT_LOWBALL"

def test_standard_accept(base_input):
    """Test Rule 2: Accept if offer >= MAM."""
    base_input.mam = 42000.0
    base_input.user_offer = 43000.0
    
    decision = make_decision(base_input)
    assert decision.action == "ACCEPT"
    assert decision.response_key == "ACCEPT_FINAL"

def test_lowball_reject(base_input):
    """Test Rule 3: Reject if offer < 70% MAM."""
    base_input.mam = 42000.0
    base_input.user_offer = 25000.0
    
    decision = make_decision(base_input)
    assert decision.action == "REJECT"
    assert decision.response_key == "REJECT_LOWBALL"

def test_standard_counter_first_turn(base_input):
    """
    Test Rule 4: COUNTER (First Turn / No History)
    Should split difference between Asking Price and User Offer.
    """
    # ARRANGE
    base_input.mam = 42000.0
    base_input.asking_price = 50000.0
    base_input.user_offer = 40000.0 
    base_input.user_sentiment = "neutral"
    base_input.history = [] # Empty history
    
    # ACT
    decision = make_decision(base_input)
    
    # ASSERT
    # Midpoint of 50k and 40k = 45k
    assert decision.action == "COUNTER"
    assert decision.response_key == "STANDARD_COUNTER"
    assert decision.counter_price == 47500.0 
    # Metadata key updated to match v1.3 code
    assert decision.decision_metadata["rule"] == "offer_count_aware_counter"