import pytest
from app.strategy_core import make_decision
from app.schemas import StrategyInput

@pytest.fixture
def base_input():
    return StrategyInput(
        mam=40000.0,
        asking_price=50000.0,
        user_offer=45000.0, 
        user_intent="MAKE_OFFER",
        user_sentiment="neutral",
        session_id="sess_edge_cases",
        history=[]
    )

def test_negative_offer(base_input):
    """Test what happens if the user offers a negative amount."""
    base_input.user_offer = -5000.0
    
    decision = make_decision(base_input)
    
    # Needs to trigger lowball reject because -5000.0 < 40000 * 0.7 (28000.0)
    assert decision.action == "REJECT"
    assert decision.response_key == "REJECT_LOWBALL"

def test_offer_greater_than_asking_price(base_input):
    """Test what happens if the user offers higher than the asking price."""
    base_input.user_offer = 60000.0
    
    decision = make_decision(base_input)
    
    # Should automatically trigger standard accept since 60000.0 >= 40000.0
    assert decision.action == "ACCEPT"
    assert decision.response_key == "ACCEPT_FINAL"

def test_exact_mam_offer(base_input):
    """Test what happens if the user offers exactly the MAM."""
    base_input.user_offer = 40000.0
    
    decision = make_decision(base_input)
    
    # Should accept
    assert decision.action == "ACCEPT"
    assert decision.response_key == "ACCEPT_FINAL"

def test_extreme_lowball_positive_sentiment(base_input):
    """Test extreme lowball with positive sentiment."""
    base_input.user_offer = 1.0
    base_input.user_sentiment = "positive"
    
    decision = make_decision(base_input)
    
    # Sentiment does not override lowball
    assert decision.action == "REJECT"
    assert decision.response_key == "REJECT_LOWBALL"

def test_high_offer_negative_sentiment(base_input):
    """Test an offer greater than MAM but user has negative sentiment."""
    base_input.user_offer = 45000.0 # > MAM
    base_input.user_sentiment = "negative"
    
    decision = make_decision(base_input)
    
    # In strategy_core.py, the sentiment accept rule is checked first:
    # input_data.user_sentiment == 'negative' and input_data.user_offer >= sentiment_accept_threshold
    assert decision.action == "ACCEPT"
    assert decision.response_key == "ACCEPT_SENTIMENT_CLOSE"

def test_counter_when_asking_price_lower_than_mam(base_input):
    """Test logic if the system was configured incorrectly (Asking Price < MAM)."""
    base_input.asking_price = 30000.0
    base_input.mam = 40000.0
    base_input.user_offer = 35000.0
    
    decision = make_decision(base_input)
    
    # gap = 30000 - 35000 = -5000.0
    # drop_amount = -5000 * 0.25 = -1250.0
    # midpoint = 30000 - (-1250) = 31250.0
    # final_counter = min(30000, max(40000, 31250.0)) -> min(30000, 40000) -> 30000
    assert decision.action == "COUNTER"
    assert decision.counter_price == 30000.0 

def test_bot_does_not_increase_price_in_weird_history(base_input):
    """Test if user somehow lowers their offer, does the bot increase the counter?"""
    base_input.asking_price = 50000.0
    base_input.mam = 40000.0
    
    # Bot previously offered 45k
    base_input.history = [
        {"role": "assistant", "message": "45k", "counter_price": 45000.0}
    ]
    # User goes from 40k last turn (not recorded) to 20k now (weird behavior)
    base_input.user_offer = 20000.0
    
    # Gap = 45000 - 20000 = 25000
    # Concession = 0.25
    # Since 20000 < 40000 * 0.70 (28000), it should just REJECT LOWBALL
    decision = make_decision(base_input)
    assert decision.action == "REJECT"
    assert decision.response_key == "REJECT_LOWBALL"

def test_bot_counter_user_backtracks(base_input):
    """User backtracks but not to lowball zone."""
    base_input.mam = 40000.0
    base_input.history = [
        {"role": "assistant", "message": "45k", "counter_price": 45000.0}
    ]
    # user lowballs but is slightly above lowball zone (40k * 0.7 = 28k)
    base_input.user_offer = 30000.0
    
    # Gap = 45000 - 30000 = 15000
    # Drop = 15000 * 0.25 = 3750
    # Midpoint = 45000 - 3750 = 41250
    # Clamped: min(45000, max(40000, 41250)) = 41250
    decision = make_decision(base_input)
    assert decision.action == "COUNTER"
    assert decision.counter_price == 41250.0
