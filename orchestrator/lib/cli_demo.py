import requests
import sys

# 🔁 Make sure this is your orchestrator endpoint
API_URL = "http://localhost:8000/ina/v1/chat"

# Use the session ID you already initialized in Redis
SESSION_ID = "Ashna"  # ⚡ change this to your actual session key in Redis

def send_message(user_id, message):
    payload = {
        "user_id": user_id,
        "message": message
    }

    try:
        response = requests.post(API_URL, json=payload, timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "[No response field found]")

    except requests.exceptions.RequestException as e:
        return f"[ERROR] API call failed: {e}"
    except ValueError:
        return "[ERROR] Invalid JSON response from server"


def main():
    print("\n🤖 Negotiation Bot CLI Demo")
    print("Type 'exit' or 'quit' to stop\n")
    print(f"🔑 Session ID: {SESSION_ID}\n")

    while True:
        user_input = input("You: ").strip()

        if user_input.lower() in {"exit", "quit"}:
            print("\n👋 Ending session. Bye!")
            sys.exit(0)

        bot_reply = send_message(SESSION_ID, user_input)
        print(f"Bot: {bot_reply}\n")


if __name__ == "__main__":
    main()
