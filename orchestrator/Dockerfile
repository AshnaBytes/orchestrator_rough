FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir fastapi uvicorn httpx redis langgraph langchain-core slowapi

# 🔥 IMPORTANT: copy whole project (not just orchestrator)
COPY . .

# Set PYTHONPATH so 'orchestrator' is recognized
ENV PYTHONPATH=/app

EXPOSE 10000

CMD ["uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "10000"]
