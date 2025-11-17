# Purpose: Unit tests for the core negotiation logic (v1.2).

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
    v1.1 Update: Includes default 'intent' and 'sentiment'.
    """
    return StrategyInput(
        mam=42000.0,
        asking_price=50000.0,
        user_offer=45000.0,  # Note: this default will trigger ACCEPT
        
        # --- New v1.1 Fields ---
        user_intent="MAKE_OFFER",
        user_sentiment="neutral", # Default to neutral
        # ---------------------
        
        session_id="sess_test_fixture",
        history=[]
    )

# =======================================================================
#  New Test Case for v1.2 Logic
# =======================================================================

def test_accept_on_negative_sentiment(base_input, caplog):
    """
    Test Rule 1: ACCEPT (Sentiment Rule)
    If user is 'negative' and their offer is "close enough" (>= 95% of MAM),
    we must accept to save the deal.
    """
    # Arrange
    base_input.mam = 42000.0
    base_input.user_sentiment = "negative" # <-- The trigger
    
    # Offer is 40,000. MAM is 42,000. (Standard logic would REJECT)
    # 95% threshold is 42,000 * 0.95 = 39,900
    # Since 40,000 > 39,900, this rule should fire.
    base_input.user_offer = 40000.0
    
    # Act
    with caplog.at_level(logging.WARNING):
        decision = make_decision(base_input)
    
    # Assert
    assert decision.action == "ACCEPT"
    assert decision.response_key == "ACCEPT_SENTIMENT_CLOSE" # The new key
    assert decision.counter_price == 40000.0
    assert decision.decision_metadata["rule"] == "sentiment_accept_on_negative"
    assert "ACCEPT (Sentiment Rule)" in caplog.text # Check the log

def test_sentiment_rule_does_not_fire_if_offer_too_low(base_input):
    """
    Test that the sentiment rule *doesn't* fire if the user is
    'negative' but their offer is still too low (e.g., a lowball).
    """
    # Arrange
    base_input.mam = 42000.0
    base_input.user_sentiment = "negative"
    
    # Offer is 30,000. 95% threshold is 39,900.
    # This should *fail* the sentiment rule and fall through
    # to the "Lowball REJECT" rule.
    base_input.user_offer = 25000.0
    
    # Act
    decision = make_decision(base_input)
    
    # Assert
    # It should NOT be 'ACCEPT'
    assert decision.action == "REJECT"
    assert decision.response_key == "REJECT_LOWBALL"
    assert decision.decision_metadata["rule"] == "user_offer_lt_lowball_threshold"

def test_sentiment_rule_does_not_fire_if_sentiment_positive(base_input):
    """
    Test that the rule doesn't fire if sentiment is 'positive',
    even if the offer is in the 95% range.
    """
    # Arrange
    base_input.mam = 42000.0
    base_input.user_sentiment = "positive" # <-- Not negative
    base_input.user_offer = 40000.0 # (In the 95% range)
    
    # Act
    # This should fail Rule 1, fail Rule 2 (offer < mam),
    # and become a standard COUNTER offer.
    decision = make_decision(base_input)
    
    # Assert
    assert decision.action == "COUNTER"
    assert decision.response_key == "STANDARD_COUNTER"

# =======================================================================
#  Existing v1.0 Tests (No changes needed thanks to the fixture)
# =======================================================================

def test_unbreakable_rule_accept_offer_above_mam(base_input):
    """
    Test Rule 2: ACCEPT (Standard)
    If user_offer is greater than mam, we MUST accept.
    """
    # Arrange
    base_input.user_offer = 43000.0
    base_input.mam = 42000.0
    
    # Act
    decision = make_decision(base_input)
    
    # Assert
    assert decision.action == "ACCEPT"
    assert decision.response_key == "ACCEPT_FINAL"
    assert decision.counter_price == 43000.0
    assert decision.decision_metadata["rule"] == "user_offer_gte_mam"

def test_unbreakable_rule_accept_offer_equals_mam(base_input):
    """
    Test Edge Case for Rule 2: ACCEPT (Standard)
    If user_offer is exactly equal to mam, we MUST accept.
    """
    # Arrange
    base_input.user_offer = 42000.0
    base_input.mam = 42000.0
    
    # Act
    decision = make_decision(base_input)
    
    # Assert
    assert decision.action == "ACCEPT"
    assert decision.response_key == "ACCEPT_FINAL"

def test_lowball_reject(base_input):
    """
    Test Rule 3: REJECT (Lowball)
    If user_offer is < 70% of mam.
    """
    # Arrange
    base_input.mam = 42000.0
    base_input.user_offer = 25000.0 # This is < (42000 * 0.7 = 29400)
    
    # Act
    decision = make_decision(base_input)
    
    # Assert
    assert decision.action == "REJECT"
    assert decision.response_key == "REJECT_LOWBALL"
    assert decision.counter_price is None

def test_standard_counter(base_input):
    """
    Test Rule 4: COUNTER
    Offer is > lowball threshold but < mam.
    """
    # Arrange
    base_input.mam = 42000.0
    base_input.asking_price = 50000.0
    base_input.user_offer = 40000.0 # > 29400 (lowball) and < 42000 (mam)
    base_input.user_sentiment = "neutral" # Not negative
    
    # Act
    decision = make_decision(base_input)
    
    # Assert
    assert decision.action == "COUNTER"
    assert decision.response_key == "STANDARD_COUNTER"
    assert decision.counter_price == 45000.0 
    assert decision.decision_metadata["rule"] == "standard_counter_midpoint"