from typing import TypedDict, List, Dict, Any


class AgentState(TypedDict, total=False):
    session_id: str
    mam: float
    asking_price: float
    user_input: str
    history: List[Dict[str, Any]]

    # NLU outputs
    intent: str
    sentiment: str
    user_offer: float

    # Brain outputs
    brain_action: str
    counter_price: float
    response_key: str

    # Final
    final_response: str
    
    # Internal
    _brain_raw: Dict[str, Any]
