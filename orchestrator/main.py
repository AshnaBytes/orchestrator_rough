import os
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from orchestrator.lib import state_manager
from orchestrator.lib.brain_client import call_brain
from orchestrator.lib.nlu_client import call_nlu
from orchestrator.lib.ms5_client import call_mouth

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("orchestrator")

app = FastAPI(title="INA Orchestrator")


# ---------------------- Schemas ----------------------
class ChatInput(BaseModel):
    user_id: str
    message: str


class ChatOutput(BaseModel):
    response: str


# ---------------------- Health ----------------------
@app.get("/")
async def home():
    return {"message": "Orchestrator is running!"}


@app.get("/ping-redis")
async def ping_redis():
    ok = await state_manager.ping_redis()
    if not ok:
        raise HTTPException(status_code=503, detail="Redis not reachable")

    test_sid = "ping-test-session"
    success = await state_manager.set_session(test_sid, {"hello": "redis"})
    data = await state_manager.get_session(test_sid)

    return {"redis_ping": ok, "write_ok": success, "read_data": data}


@app.get("/health")
async def health_check():
    redis_ok = await state_manager.ping_redis()
    return {"status": "ok" if redis_ok else "degraded"}


# ---------------------- MAIN CHAT ----------------------

@app.post("/ina/v1/chat", response_model=ChatOutput)
async def chat_endpoint(payload: ChatInput):

    try:
        # 1️⃣ Validate existing Redis state (Push Model)
        session_id = f"session:{payload.user_id}"
        session = await state_manager.get_session(session_id)

        if not session:
            raise HTTPException(
                status_code=400,
                detail="Session not initialized. Backend must call /session/init."
            )

        # 2️⃣ Append user message to history
        session["messages"].append({
            "from": "user",
            "text": payload.message
        })
        history = session["messages"]

        
        # ======================================================
        # 🛡️ SATURDAY HARDENING STARTS HERE
        # ======================================================

        # 3️⃣ NLU (SAFE)
        try:
            nlu = await call_nlu(payload.message, session_id=session_id)
        except Exception as e:
            logger.exception("NLU failed, using fallback")
            nlu = {
                "intent": "unknown",
                "sentiment": "neutral",
                "entities": {}
            }

        user_intent = nlu.get("intent", "unknown")
        user_sentiment = nlu.get("sentiment", "neutral")
        user_offer = nlu.get("entities", {}).get("PRICE", 0)

        # Business inputs (unchanged)
        mam = 150.0
        asking_price = 200.0

        # 4️⃣ Brain (SAFE)
        try:
            brain = await call_brain(
                mam=mam,
                asking_price=asking_price,
                user_offer=user_offer,
                user_intent=user_intent,
                user_sentiment=user_sentiment,
                session_id=session_id,
                history=history,
            )
        except Exception as e:
            logger.exception("Brain failed, using fallback")
            brain = {
                "action": "COUNTER",
                "response_key": "STANDARD_COUNTER",
                "counter_price": 0.0
            }

        logger.info(f"[MS4] Brain returned: {brain}")

        

        # 5️⃣ Mouth (SAFE)
        try:
            ms5_resp = await call_mouth(brain)
            if not ms5_resp or "response_text" not in ms5_resp:
                raise ValueError("Invalid mouth response")
            ai_response = ms5_resp["response_text"]
        except Exception as e:
            logger.exception("Mouth failed, using fallback")
            ai_response = "Let me think about that for a moment. Could you please try again?"

        #orginal ms5 call
        # 5️⃣ Mouth (SAFE)
      #  try:
      #      ms5_resp = await call_mouth(brain)
      #      ai_response = ms5_resp.get(
      #          "response_text",
      #          "Let me think about that for a moment. Could you please try again?"
      #      )
      #  except Exception as e:
      #      logger.exception("Mouth failed, using fallback")
      #      ai_response = "Let me think about that for a moment. Could you please try again?"

        # ======================================================
        # 🛡️ SATURDAY HARDENING ENDS HERE
        # ======================================================

        # 6️⃣ Save AI message back to Redis
        session["messages"].append({
            "from": "ina",
            "text": ai_response,
            "brain_action": brain.get("action"),
            "brain_key": brain.get("response_key")
        })

        await state_manager.set_session(session_id, session)

        return ChatOutput(response=ai_response)

    except HTTPException:
        raise

    except Exception as e:
        logger.exception(f"Unexpected error for {payload.user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------- Shutdown ----------------------
@app.on_event("shutdown")
async def shutdown_event():
    await state_manager.close_redis()
