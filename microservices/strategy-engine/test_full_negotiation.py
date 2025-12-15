# Purpose: Simulates a full, multi-turn negotiation against the running API.
# This validates the "Brain's" state management and price convergence.

import requests
import json
import uuid
import time

# --- Configuration ---
API_URL = "http://127.0.0.1:8000/decide"
SESSION_ID = f"sim_{str(uuid.uuid4())[:8]}"

# --- Scenario Setup ---
# A realistic scenario where the user starts low and slowly moves up.
MAM = 40000.0           # Our secret floor
ASKING_PRICE = 50000.0  # What we listed it for
STARTING_OFFER = 30000.0 # User starts low
USER_INCREMENT = 2000.0  # User increases offer by $1.5k each turn

def run_simulation():
    print("\n" + "="*60)
    print(f"🤖 STARTING NEGOTIATION SIMULATION")
    print(f"Session ID: {SESSION_ID}")
    print(f"Context: Asking ${ASKING_PRICE:,.0f} | MAM ${MAM:,.0f}")
    print("="*60 + "\n")

    # Initialize State
    history = []
    current_user_offer = STARTING_OFFER
    turn_count = 1

    while True:
        # 1. Build the Payload (Mimicking the Orchestrator)
        payload = {
            "mam": MAM,
            "asking_price": ASKING_PRICE,
            "user_offer": current_user_offer,
            "user_intent": "MAKE_OFFER",
            "user_sentiment": "neutral",
            "session_id": SESSION_ID,
            "history": history
        }

        # 2. Call the "Brain" API
        try:
            response = requests.post(API_URL, json=payload)
            response.raise_for_status()
            decision = response.json()
        except requests.exceptions.ConnectionError:
            print("❌ ERROR: Could not connect to the API.")
            print("   Make sure the server is running: uvicorn app.main:app --reload")
            break
        except Exception as e:
            print(f"❌ CRITICAL ERROR: {e}")
            break

        # 3. Extract Decision Data
        action = decision['action']
        key = decision['response_key']
        counter = decision['counter_price']
        meta = decision.get('decision_metadata', {})

        # 4. Print the Turn Details
        print(f"🔄 TURN {turn_count}")
        print(f"   👤 User Offer:   ${current_user_offer:,.0f}")
        
        if counter:
            print(f"   🤖 Bot Counter:  ${counter:,.0f}  (Action: {action} | Key: {key})")
            # Print the math logic used if available
            if "concession_factor" in meta:
                print(f"      [Debug] Factor: {meta['concession_factor']} | Rule: {meta.get('rule')}")
        else:
            print(f"   🤖 Bot Action:   {action} ({key})")

        print("-" * 30)

        # 5. Handle End Game
        if action in ["ACCEPT", "REJECT"]:
            print(f"\n✅ NEGOTIATION ENDED: The Bot decided to {action}.")
            print(f"   Final Price: ${current_user_offer:,.0f}")
            break
        
        # 6. Prepare Next Turn (Update History)
        # This simulates the Orchestrator updating the conversation log
        history.append({
            "role": "user", 
            "message": f"I offer {current_user_offer}", 
            "offer": current_user_offer
        })
        
        # We assume the user sees the counter and responds
        history.append({
            "role": "assistant", 
            "message": f"I counter {counter}", 
            "counter_price": counter
        })
        
        # Simulate User increasing their offer for next round
        current_user_offer += USER_INCREMENT
        turn_count += 1
        
        # Safety Break loop to prevent infinite runs
        if turn_count > 15:
            print("\n FORCE STOP: Negotiation went too long (>15 turns).")
            break
            
        time.sleep(1) # Pause for readability

if __name__ == "__main__":
    run_simulation()