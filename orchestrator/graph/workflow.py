from langgraph.graph import StateGraph
from orchestrator.graph.state import AgentState
from orchestrator.graph.nodes import nlu_node, brain_node, mouth_node, fast_track_node
from orchestrator.lib.intents import Intent


# Intents that bypass the Strategy Engine and go directly to the Phraser
FAST_TRACK_INTENTS = {
    Intent.GREET,
    Intent.BYE,
    Intent.DEAL,
    Intent.ASK_PREVIOUS_OFFER,
    Intent.ASK_QUESTION,
}


def route_after_nlu(state: AgentState) -> str:
    """
    Router — single source of truth for intent-based routing.
    Uses only the NLU's detected intent. Never guesses or infers.

    Fast-track (skip Strategy Engine):
        GREET, BYE, DEAL, ASK_PREVIOUS_OFFER

    Full pipeline (Strategy Engine → Phraser):
        MAKE_OFFER, ASK_QUESTION, UNKNOWN (and any unexpected value)
    """
    intent = state.get("intent", Intent.UNKNOWN)

    if intent == Intent.INVALID:
        return "__end__"

    if intent in FAST_TRACK_INTENTS:
        return "fast_track"

    return "brain"


def build_workflow():
    graph = StateGraph(AgentState)

    graph.add_node("nlu", nlu_node)
    graph.add_node("brain", brain_node)
    graph.add_node("fast_track", fast_track_node)
    graph.add_node("mouth", mouth_node)

    graph.set_entry_point("nlu")

    # Intent-based conditional routing after NLU
    graph.add_conditional_edges("nlu", route_after_nlu)

    # Both paths converge at the Phraser
    graph.add_edge("brain", "mouth")
    graph.add_edge("fast_track", "mouth")

    return graph.compile()
