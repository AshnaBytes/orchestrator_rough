import os
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from orchestrator.lib import state_manager
from orchestrator.lib.backend_client import get_rules_from_backend
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
        # 1️⃣ Load session
        session_id = f"session:{payload.user_id}"
        session = await state_manager.get_session(session_id) or {"messages": []}

        session["messages"].append({"from": "user", "text": payload.message})
        history = session["messages"]

        # 2️⃣ NLU (MS2)
        nlu = await call_nlu(payload.message, session_id=session_id)
        user_intent = nlu["intent"]
        user_sentiment = nlu["sentiment"]
        user_offer = nlu["entities"].get("PRICE") or 0

        # Fake backend values (for now)
        mam = 150.0
        asking_price = 200.0

        # 3️⃣ Strategy Engine (MS4)
        brain = await call_brain(
            mam=mam,
            asking_price=asking_price,
            user_offer=user_offer,
            user_intent=user_intent,
            user_sentiment=user_sentiment,
            session_id=session_id,
            history=history,
        )

        logger.info(f"Brain responded: {brain}")

        # 4️⃣ Mouth (MS5)
        ms5_resp = await call_mouth(brain)

        ai_response = ms5_resp.get(
            "response_text",
            "[SYSTEM] Could not generate phrase."
        )


        # 5️⃣ Save to Redis
        session["messages"].append({"from": "ina", "text": ai_response})
        await state_manager.set_session(session_id, session)

        # 6️⃣ Return final response
        return ChatOutput(response=ai_response)

    except Exception as e:
        logger.exception(f"Error in chat flow for user {payload.user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during chat flow")


# ---------------------- Shutdown ----------------------
@app.on_event("shutdown")
async def shutdown_event():
    await state_manager.close_redis()
