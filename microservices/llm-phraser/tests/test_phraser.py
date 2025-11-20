# E:\FYP\llm-phraser\tests\test_phraser.py
# (Fixed with dependency override and proper async mocking)

import pytest
from fastapi.testclient import TestClient
from app.main import app, get_groq_client  # <-- Import the dependency to override
from app.schemas import PhraserInput
from unittest.mock import MagicMock, AsyncMock, patch

# --- The Fix: Dependency Override ---

# 1. Create a mock client object. This can be a simple MagicMock.
mock_groq_client = MagicMock()

# 2. Define your override function. This function will be run
#    *instead of* the real 'get_groq_client'.
def override_get_groq_client():
    """A mock dependency that returns our mock client."""
    return mock_groq_client

# 3. Apply the override to the FastAPI app *before* the TestClient is created.
#    This is the magic line that solves the AttributeError.
app.dependency_overrides[get_groq_client] = override_get_groq_client

# 4. Now, create the TestClient. The app's lifespan will run,
#    but our tests will never hit the real 'get_groq_client' function.
client = TestClient(app)

# ------------------------------------

def test_health_check():
    """Tests the /health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "llm-phraser"}

# Use @patch from Python's standard 'unittest.mock' library.
# We patch 'app.main.generate_llm_response' because that's where
# it's imported and used by the '/phrase' endpoint.
# 'new_callable=AsyncMock' is CRITICAL for mocking an async function.
@patch("app.main.generate_llm_response", new_callable=AsyncMock)
def test_generate_phrase_success(mock_generate_llm_call: AsyncMock):
    """
    Tests the /phrase endpoint with a mocked LLM call.
    The mock_generate_llm_call is injected by @patch.
    """
    
    # 1. ARRANGE
    
    # This is the fake response we want our mock LLM function to return
    mock_response_text = "This is a successful mock counter-offer at $48,000."
    mock_generate_llm_call.return_value = mock_response_text

    # This is the JSON payload we will send
    test_payload = {
        "action": "COUNTER",
        "response_key": "STANDARD_COUNTER",
        "counter_price": 48000.0,
        "policy_type": "rule-based",
        "policy_version": "1.1.0"
    }

    # 2. ACT
    # Send the POST request to the TestClient
    response = client.post("/phrase", json=test_payload)

    # 3. ASSERT
    
    # Check for a successful response
    assert response.status_code == 200
    assert response.json() == {"response_text": mock_response_text}

    # Check that our mock function was called correctly
    mock_generate_llm_call.assert_called_once()
    
    # Get the arguments it was called with
    call_args = mock_generate_llm_call.call_args[0] # Get positional args
    
    # Check that the first argument was a PhraserInput object
    assert isinstance(call_args[0], PhraserInput)
    assert call_args[0].response_key == "STANDARD_COUNTER"
    
    # Check that the second argument was our injected mock client
    assert call_args[1] is mock_groq_client

@patch("app.main.generate_llm_response", new_callable=AsyncMock)
def test_generate_phrase_llm_error(mock_generate_llm_call: AsyncMock):
    """
    Tests how the API behaves if the LLM call fails.
    """
    # 1. ARRANGE
    # This time, we mock the function to raise an exception
    mock_generate_llm_call.side_effect = Exception("Simulated Groq API Error")

    test_payload = {
        "action": "REJECT",
        "response_key": "REJECT_LOWBALL",
        "policy_type": "rule-based",
        "policy_version": "1.1.0"
    }

    # 2. ACT
    response = client.post("/phrase", json=test_payload)

    # 3. ASSERT
    # We should get a 500 Internal Server Error
    assert response.status_code == 500
    assert "An internal server error occurred" in response.json()["detail"]