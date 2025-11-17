# INA Strategy Engine (MS 4 - "The Brain")

[![Policy Version](https://img.shields.io/badge/Policy-Rule--Based-blue.svg)](app/strategy_core.py)
[![Policy Version](https://img.shields.io/badge/Version-1.1.0-blue.svg)](app/strategy_core.py)
[![Test Coverage](https://img.shields.io/badge/Coverage-100%25-brightgreen.svg)](tests/test_strategy.py)

This repository contains the `strategy-engine` microservice, a core component of the Integrative Negotiation Agent (INA) Platform.

## 1. 🧠 Purpose: The "Hybrid Brain"

This service (MS 4) acts as the secure, rule-based "Brain" of the negotiation chatbot. Its one and only job is to make the final financial decision.

It follows the "Hybrid Brain" architecture:
1.  It **RECEIVES** sensitive financial data (like the **Minimum Acceptable Margin**, or `mam`) from the Orchestrator (MS 1).
2.  It **DECIDES** the next action (ACCEPT, REJECT, COUNTER) based on a secure, non-LLM, rule-based policy.
3.  It **RETURNS** a *command* (e.g., `{"action": "COUNTER", "counter_price": 48000}`) back to the Orchestrator.

This service is the **only** component that ever sees the `mam`. The LLM service (MS 5, "The Mouth") **never** sees this secret data, eliminating the risk of an LLM leaking a financial floor.

---

## 2. 📜 API Contract (v1)

The service exposes one primary endpoint: `POST /decide`.

### Endpoint: `POST /decide`

This endpoint receives the full context and returns a single, decisive command.

#### Request Body: `StrategyInput`

```json
{
    "mam": 42000.0,
    "asking_price": 50000.0,
    "user_offer": 45000.0,
    "session_id": "sess_12345abc",
    "history": [
        {"role": "bot", "action": "GREET"},
        {"role": "user", "offer": 45000.0}
    ]
}
```
* `mam` (float, **required**): The secret financial floor.
* `asking_price` (float, **required**): The initial price offered by the business.
* `user_offer` (float, **required**): The latest price offered by the user.
* `session_id` (str, **required**): Unique session identifier.
* `history` (list[dict], optional): A log of previous conversation turns.

#### Response Body: `StrategyOutput`

This service *never* returns the `mam`. It only returns a command.

**Example 1: COUNTER Response**
```json
{
    "action": "COUNTER",
    "response_key": "STANDARD_COUNTER",
    "counter_price": 48000.0,
    "policy_type": "rule-based",
    "policy_version": "1.1.0",
    "decision_metadata": {
        "rule": "standard_counter_midpoint",
        "mam": 42000.0,
        "user_offer": 45000.0,
        "asking_price": 50000.0,
        "calculated_counter": 48000.0
    }
}
```

**Example 2: ACCEPT Response**
```json
{
    "action": "ACCEPT",
    "response_key": "ACCEPT_FINAL",
    "counter_price": 46000.0,
    "policy_type": "rule-based",
    "policy_version": "1.1.0",
    "decision_metadata": {
        "rule": "user_offer_gte_mam",
        "mam": 42000.0,
        "user_offer": 46000.0
    }
}
```

* `action` (str): One of `ACCEPT`, `REJECT`, or `COUNTER`.
* `response_key` (str): A key for MS 5 (The Mouth) to select a response template (e.g., `REJECT_LOWBALL`).
* `counter_price` (float | null): The price to send back. This is `null` for `REJECT` actions.
* `policy_type` (str): `rule-based` for this implementation.
* `policy_version` (str): The semantic version of the logic in `strategy_core.py`.
* `decision_metadata` (dict): A rich, auditable log of the values and rules used to make this decision.

---

## 3. 🚀 How to Run

You can run the service locally for development or as a Docker container.

### A. Local Development (with Virtual Environment)

1.  **Create & Activate Environment** (Requires Python 3.11+)
    ```bash
    python -m venv .venv
    .\.venv\Scripts\activate
    ```

2.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run the Service** (with hot-reloading)
    ```bash
    uvicorn app.main:app --reload
    ```
    The service will be available at `http://127.0.0.1:8000`.
    * Health Check: `http://127.0.0.1:8000/health`
    * API Docs: `http://127.0.0.1:8000/docs`

### B. Docker (Recommended)

This method spins up both the `strategy-engine` and a `redis` container (simulating MS 3).

1.  **Prerequisite:** Ensure Docker Desktop is running.

2.  **Build and Run Containers**
    Run this from the project root (where `docker-compose.yml` is):
    ```bash
    docker-compose up -d --build
    ```

3.  **Verify**
    The service will be available at `http://127.0.0.1:8000`.
    You can check the logs with:
    ```bash
    docker-compose logs -f strategy-engine
    ```

4.  **Stop Containers**
    ```bash
    docker-compose down
    ```

---

## 4. 🧪 How to Run Tests

We use `pytest` for unit testing and `pytest-cov` for coverage.

1.  **Install Dev Dependencies**
    ```bash
    pip install -r requirements-dev.txt
    ```

2.  **Run All Tests**
    ```bash
    pytest
    ```

3.  **Run Tests with Coverage Report**
    This report targets *only* the `strategy_core.py` logic file.
    ```bash
    pytest --cov=app.strategy_core --cov-report=term-missing
    ```
    **Target: 100% coverage on `app/strategy_core.py`**

---

## 5. 🤖 Future: Migrating to Reinforcement Learning (RL)

This service was designed to be "pluggable." The current `rule-based` policy can be swapped out for a trained RL policy with minimal changes to the API layer.

### The Interface

The `make_decision` function in `app/strategy_core.py` is the key.

```python
def make_decision(input_data: StrategyInput) -> StrategyOutput:
    # ... logic ...
    return StrategyOutput(...)
```

### High-Level Migration Steps

1.  **Create `app/rl_policy.py`:** A new module will be created to house the RL model logic.
2.  **Load the Model:** This file will be responsible for loading the trained model file (e.g., `model.pkl` from `wandb` or S3) into memory *once* at startup.
3.  **Create `make_rl_decision()`:** This new function will conform to the *exact same interface*:
    * It will accept `StrategyInput` as its argument.
    * It will *pre-process* this input into a feature vector (a `numpy` array or `torch` tensor) that the model expects.
    * It will call `model.predict(features)` to get a decision.
    * It will *post-process* the model's output (e.g., an action `[0, 1, or 2]`) back into a valid `StrategyOutput` schema.
4.  **Apply Guardrails:** The `make_rl_decision` function **MUST** re-apply the "Unbreakable Rule" *after* getting the model's prediction.
    ```python
    # Inside make_rl_decision()
    
    # 1. Unbreakable Rule
    if input_data.user_offer >= input_data.mam:
        return # ... the ACCEPT response
        
    # 2. If no accept, THEN ask the model
    prediction = model.predict(...)
    
    # 3. Post-process and return
    return # ... the model's COUNTER/REJECT response
    ```
5.  **Update `main.py`:** The final step is to change a single line in `app/main.py` to import and use the new policy.
    ```python
    # Change this:
    # from .strategy_core import make_decision
    
    # To this:
    from .rl_policy import make_rl_decision as make_decision
    
    # ... the @app.post("/decide") endpoint remains unchanged.
    ```