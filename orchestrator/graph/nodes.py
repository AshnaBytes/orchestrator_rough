from orchestrator.graph.state import AgentState
from orchestrator.lib.nlu_client import call_nlu
from orchestrator.lib.brain_client import call_brain
from orchestrator.lib.phraser_client import call_phraser
import logging

logger = logging.getLogger("orchestrator_nodes")


# ---------- NLU NODE ----------
async def nlu_node(state: AgentState):

    try:
        nlu = await call_nlu(
            state["user_input"],
            session_id=state["session_id"]
        )

    except Exception as e:
        # Safe fallback if NLU fails
        nlu = {
            "intent": "unknown",
            "sentiment": "neutral",
            "entities": {}
        }

    state["intent"] = nlu.get("intent", "unknown")
    state["sentiment"] = nlu.get("sentiment", "neutral")
    state["user_offer"] = nlu.get("entities", {}).get("PRICE", 0)

    logger.info("NLU RAW: %s", nlu)


    return state


# ---------- BRAIN NODE ----------
async def brain_node(state: AgentState):

    try:
        brain = await call_brain(
            mam=state["mam"],
            asking_price=state["asking_price"],
            user_offer=state.get("user_offer", 0),
            user_intent=state.get("intent", "unknown"),
            user_sentiment=state.get("sentiment", "neutral"),
            session_id=state["session_id"],
            history=state.get("history", []),
        )

    except Exception:
        # Safe fallback if Brain fails
        brain = {
            "action": "COUNTER",
            "counter_price": state["asking_price"],
            "response_key": "SAFE_FALLBACK",
            # 🔥 REQUIRED BY MS5 SCHEMA
            "policy_type": "rule-based",
            "policy_version": "fallback",
            "decision_metadata": {"reason": "brain_failed"}
        }

    # ⭐ Structured state mapping
    state["brain_action"] = brain.get("action")
    state["counter_price"] = brain.get("counter_price")
    state["response_key"] = brain.get("response_key")

    
    # ⭐ Guarantee MS5 contract fields
    brain.setdefault("policy_type", "rule-based")
    brain.setdefault("policy_version", "v1")
    brain.setdefault("decision_metadata", {})

    # ⭐ RAW brain output for Mouth
    state["_brain_raw"] = brain
    logger.info("BRAIN RAW: %s", brain)


    return state

# ----------- MOUTH NODE ----------

async def mouth_node(state: AgentState):

    brain = state.get("_brain_raw")

    if not brain:
        state["final_response"] = "Brain missing. Please repeat."
        return state

    try:
        ms5 = await call_phraser(brain)

        logger.info("PHRASER RAW RESPONSE: %s", ms5)

        # ⭐ UNIVERSAL EXTRACTION
        response_text = (
            ms5.get("response_text")
            or ms5.get("response")
            or ms5.get("text")
            or ms5.get("message")
        )

        # ⭐ Nested extraction
        if not response_text and isinstance(ms5.get("data"), dict):
            response_text = (
                ms5["data"].get("response_text")
                or ms5["data"].get("response")
                or ms5["data"].get("text")
            )

        if not response_text:
            response_text = str(ms5)

        state["final_response"] = response_text

    except Exception as e:
        print("Mouth Error:", e)
        state["final_response"] = "System is thinking. Please try again."

    return state
