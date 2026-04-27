"""Quick script to simulate a WhatsApp conversation with the bot."""
import requests
import time

BASE = "http://localhost:5000"
PHONE = "+60123456789"


def send(msg):
    r = requests.post(f"{BASE}/webhook", json={"phone": PHONE, "message": msg})
    data = r.json()
    print(f"\nYou: {msg}")
    print(f"Bot: {data['reply']}")
    if data.get("lead_complete"):
        print("\n--- Lead captured! ---")
        print(data["lead_data"])
    time.sleep(1)  # small delay between messages
    return data


if __name__ == "__main__":
    print("=== Tuition Centre Lead Bot - Chat Simulator ===\n")

    send("Hi, do you have maths class for Form 3?")
    send("Yes, my son is interested. His name is Ahmad.")
    send("I'm Puan Siti. Evenings would be best, maybe Tuesday and Thursday?")
    send("That sounds good, thank you!")

    # Check leads
    print("\n\n--- All Collected Leads ---")
    r = requests.get(f"{BASE}/leads")
    print(r.json())
