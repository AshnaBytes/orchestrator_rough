import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from orchestrator.lib import state_manager
from orchestrator.graph.workflow import build_workflow

# Setup logging first
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("orchestrator")

# 🔥 Build Graph Once (Startup Time)
graph_app = build_workflow()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    logger.info("INA Orchestrator starting up...")
    yield
    logger.info("INA Orchestrator shutting down...")
    await state_manager.close_redis()


app = FastAPI(title="INA Orchestrator", lifespan=lifespan)


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
        # ------------------------------------------------
        # 1️⃣ Push Model → Validate Redis Session
        # ------------------------------------------------
        session_id = f"session:{payload.user_id}"
        session = await state_manager.get_session(session_id)

        if not session:
            logger.warning(f"Session not found for {session_id}. Using defaults.")
            session = {
                "messages": [],
                "mam": 150.0,
                "asking_price": 200.0
            }

        # ------------------------------------------------
        # 2️⃣ Append User Message
        # ------------------------------------------------
        session["messages"].append({
            "from": "user",
            "text": payload.message
        })

        history = session["messages"]

        # ------------------------------------------------
        # 3️⃣ Business Inputs (Pulled from Redis Session)
        # ------------------------------------------------
        mam = float(session.get("mam", 150.0))
        asking_price = float(session.get("asking_price", 200.0))

        # ------------------------------------------------
        # 4️⃣ LANGGRAPH EXECUTION (🔥 NEW CORE)
        # ------------------------------------------------
        try:
            state = {
                "session_id": session_id,
                "mam": mam,
                "asking_price": asking_price,
                "user_input": payload.message,
                "history": history,
            }

            result = await graph_app.ainvoke(state)

            ai_response = result.get(
                "final_response",
                "Let me think about that for a moment."
            )

            brain_action = result.get("brain_action")
            brain_key = result.get("response_key")

        except Exception as e:
            logger.exception("Graph failed, using safe fallback")
            ai_response = "Let me think about that for a moment. Could you please try again?"
            brain_action = "FALLBACK"
            brain_key = "GRAPH_FAIL"

        # ------------------------------------------------
        # 5️⃣ Save AI Response Back To Redis
        # ------------------------------------------------
        session["messages"].append({
            "from": "ina",
            "text": ai_response,
            "brain_action": brain_action,
            "brain_key": brain_key
        })

        await state_manager.set_session(session_id, session)

        return ChatOutput(response=ai_response)

    except HTTPException:
        raise

    except Exception as e:
        logger.exception(f"Unexpected error for {payload.user_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

