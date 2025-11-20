# INA LLM Phraser (MS 5 - "The Mouth")

[![Service Type](https://img.shields.io/badge/Service-LLM%20Sandbox-red.svg)](app/main.py)
[![LLM Provider](https://img.shields.io/badge/LLM-Groq%20(Llama3)-purple.svg)](app/llm_client.py)
[![Test Coverage](https://img.shields.io/badge/Coverage-Pending-yellow.svg)](tests/test_phraser.py)

This repository contains the `llm-phraser` microservice, the sandboxed "Mouth" of the Integrative Negotiation Agent (INA) Platform.

## 1. 👄 Purpose: The "Hybrid Brain" Sandbox

This service (MS 5) acts as the sandboxed, persuasive "Mouth" of the negotiation chatbot. Its only job is to phrase commands.

It is the second half of the "Hybrid Brain" architecture:
1.  It **RECEIVES** a *non-sensitive command* (e.g., `{"action": "COUNTER", "counter_price": 48000}`) from the Orchestrator (MS 1).
2.  It **NEVER** sees sensitive financial data like the `mam` (Minimum Acceptable Margin). Its API schema (`PhraserInput`) makes this impossible.
3.  It selects a prompt template based on the `response_key`.
4.  It calls the Groq API to generate a persuasive, human-like response.
5.  It **RETURNS** only the generated text (e.g., `{"response_text": "How does $48,000 sound?"}`).

This sandboxing ensures that even if the LLM is compromised, it cannot leak the negotiation's financial secrets.



---

## 2. 📜 API Contract (v1)

The service exposes one primary endpoint: `POST /phrase`.

### Endpoint: `POST /phrase`

Receives a command and returns formatted text.

#### Request Body: `PhraserInput`

*This schema is the firewall. It is structurally identical to the `StrategyOutput` from MS 4.*

```json
{
    "action": "COUNTER",
    "response_key": "STANDARD_COUNTER",
    "counter_price": 48000.0,
    "policy_type": "rule-based",
    "policy_version": "1.1.0",
    "decision_metadata": {
        "rule": "standard_counter_midpoint"
    }
}
```

#### Response Body: `PhraserOutput`

```json
{
    "response_text": "That's a bit lower than we were expecting. Based on the market, I can meet you at $48,000. How does that sound?"
}
```
---

## 3. 🚀 How to Run

### A. Local Development

1.  **Create & Activate Environment**
    ```bash
    python -m venv .venv
    .\.venv\Scripts\activate
    ```

2.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    pip install -r requirements-dev.txt
    ```

3.  **Set API Key**
    Create a `.env` file in the root and add your Groq API key:
    ```ini
    GROQ_API_KEY="gsk_YourActualGroqApiKeyHere"
    ```

4.  **Run the Service** (with hot-reloading)
    ```bash
    uvicorn app.main:app --reload
    ```
    The service will be at `http://127.0.0.1:8000`.

### B. Docker (Recommended)

This method builds the container and automatically passes in your API key from the `.env` file.

1.  **Prerequisite:** Ensure Docker Desktop is running and you have a `.env` file (see step 3 above).

2.  **Build and Run**
    ```bash
    docker-compose up -d --build
    ```

3.  **Verify**
    The service will be available at `http://127.0.0.1:8000/health`.

---

## 4. 🧪 How to Run Tests

We use `pytest` and mock all external API calls.

1.  **Install Dev Dependencies**
    ```bash
    pip install -r requirements-dev.txt
    ```

2.  **Run All Tests**
    ```bash
    pytest
    ```

3.  **Run Tests with Coverage Report**
    ```bash
    pytest --cov=app
    ```