from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Dummy Analytics Server")

class LogEntry(BaseModel):
    final_price: float
    status: str

@app.post("/analytics/log")
async def log_deal(entry: LogEntry):
    print(f"💾 Logged deal: Price={entry.final_price}, Status={entry.status}")
    return {"success": True, "received": entry}
