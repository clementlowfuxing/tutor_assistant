import os
import json
import csv
import urllib3
import requests as http_requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template

# On cloud deployment, SSL works normally. Only disable for local Zscaler proxy.
SSL_VERIFY = os.getenv("SSL_VERIFY", "true").lower() != "false"
if not SSL_VERIFY:
    urllib3.disable_warnings()

app = Flask(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# WhatsApp Business API config
WA_TOKEN = os.getenv("WA_TOKEN")           # Meta temporary access token
WA_PHONE_ID = os.getenv("WA_PHONE_ID")     # Phone Number ID from Meta dashboard
WA_VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN", "tutor_bot_verify")

LEADS_FILE = "leads.csv"
CONVERSATIONS = {}  # in-memory conversation state keyed by phone number

SYSTEM_PROMPT = """You are a friendly tuition centre assistant. Your job is to:
1. Greet the parent warmly and answer their enquiry
2. Collect the following details naturally through conversation:
   - Parent name
   - Student name
   - Student's school year/form
   - Subject(s) interested in
   - Preferred schedule (days/times)
   - Contact number (if not already known)

Rules:
- Be conversational and helpful, not robotic
- Answer common questions about classes (maths, science, English, BM available for Form 1-5)
- Classes run Mon-Sat, morning and evening slots
- Monthly fee is RM150-250 depending on subject
- Ask only ONE question at a time to avoid overwhelming the parent
- When you have enough info, confirm the details back to them

After each reply, output a JSON block on a NEW line at the very end in this exact format:
{"collected": {"parent_name": "", "student_name": "", "form": "", "subjects": "", "schedule": "", "contact": ""}, "complete": false}

Set "complete" to true only when you have at least: parent_name, student_name, form, and subjects.
Fill in fields as you learn them, leave unknown ones as empty strings."""


def init_csv():
    if not os.path.exists(LEADS_FILE):
        with open(LEADS_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "phone", "parent_name", "student_name", "form", "subjects", "schedule", "contact"])


def save_lead(phone, lead_data):
    with open(LEADS_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            datetime.now().isoformat(),
            phone,
            lead_data.get("parent_name", ""),
            lead_data.get("student_name", ""),
            lead_data.get("form", ""),
            lead_data.get("subjects", ""),
            lead_data.get("schedule", ""),
            lead_data.get("contact", phone),
        ])


def parse_ai_response(text):
    """Extract the reply message and JSON data from the AI response."""
    lines = text.strip().split("\n")
    json_data = None
    reply_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                json_data = json.loads(stripped)
            except json.JSONDecodeError:
                reply_lines.append(line)
        else:
            reply_lines.append(line)

    reply = "\n".join(reply_lines).strip()
    return reply, json_data


def chat_with_ai(phone, message):
    if phone not in CONVERSATIONS:
        CONVERSATIONS[phone] = [{"role": "system", "content": SYSTEM_PROMPT}]

    CONVERSATIONS[phone].append({"role": "user", "content": message})

    response = http_requests.post(
        GROQ_API_URL,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": GROQ_MODEL,
            "messages": CONVERSATIONS[phone],
            "temperature": 0.7,
            "max_tokens": 512,
        },
        verify=SSL_VERIFY,  # False only for Zscaler corporate proxy
    )
    response.raise_for_status()

    ai_text = response.json()["choices"][0]["message"]["content"]
    CONVERSATIONS[phone].append({"role": "assistant", "content": ai_text})

    reply, extracted = parse_ai_response(ai_text)

    if extracted and extracted.get("complete"):
        save_lead(phone, extracted["collected"])

    return reply, extracted


def send_whatsapp_message(to_phone, message):
    """Send a reply back via WhatsApp Business API."""
    http_requests.post(
        f"https://graph.facebook.com/v21.0/{WA_PHONE_ID}/messages",
        headers={
            "Authorization": f"Bearer {WA_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"body": message},
        },
        verify=SSL_VERIFY,
    )


# --- Routes ---

@app.route("/whatsapp", methods=["GET"])
def verify_webhook():
    """Meta webhook verification (required during setup)."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == WA_VERIFY_TOKEN:
        print("WhatsApp webhook verified!")
        return challenge, 200
    return "Forbidden", 403


@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    """Receive real WhatsApp messages and auto-reply."""
    body = request.json

    try:
        entry = body["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        # Skip non-message events (status updates, etc.)
        if "messages" not in value:
            return jsonify({"status": "ok"}), 200

        msg = value["messages"][0]
        phone = msg["from"]           # sender's phone number
        message = msg["text"]["body"]  # message text

        print(f"WhatsApp from {phone}: {message}")

        # Get AI reply
        reply, extracted = chat_with_ai(phone, message)

        # Send reply back via WhatsApp
        send_whatsapp_message(phone, reply)

        print(f"Replied to {phone}: {reply[:80]}...")
        if extracted and extracted.get("complete"):
            print(f"Lead captured for {phone}!")

    except (KeyError, IndexError) as e:
        print(f"Skipping non-message event: {e}")

    return jsonify({"status": "ok"}), 200

@app.route("/webhook", methods=["POST"])
def webhook():
    """Receive a message and return AI reply. Simulates WhatsApp webhook."""
    data = request.json
    phone = data.get("phone", "unknown")
    message = data.get("message", "")

    if not message:
        return jsonify({"error": "No message provided"}), 400

    if not GROQ_API_KEY:
        return jsonify({"reply": "Error: GROQ_API_KEY is not set on the server. Please set it and restart.", "lead_data": None, "lead_complete": False}), 200

    try:
        reply, extracted = chat_with_ai(phone, message)
        return jsonify({
            "reply": reply,
            "lead_data": extracted.get("collected") if extracted else None,
            "lead_complete": extracted.get("complete", False) if extracted else False,
        })
    except http_requests.exceptions.HTTPError as e:
        err_msg = f"AI API error ({e.response.status_code}): {e.response.text[:200]}"
        print(err_msg)
        return jsonify({"reply": err_msg, "lead_data": None, "lead_complete": False}), 200
    except Exception as e:
        err_msg = f"Server error: {str(e)}"
        print(err_msg)
        return jsonify({"reply": err_msg, "lead_data": None, "lead_complete": False}), 200


@app.route("/leads", methods=["GET"])
def get_leads():
    """View all collected leads."""
    leads = []
    if os.path.exists(LEADS_FILE):
        with open(LEADS_FILE, "r") as f:
            reader = csv.DictReader(f)
            leads = list(reader)
    return jsonify({"total": len(leads), "leads": leads})


@app.route("/", methods=["GET"])
def index():
    return render_template("chat.html")


# Initialize CSV on import (for gunicorn)
init_csv()


if __name__ == "__main__":
    init_csv()
    if not GROQ_API_KEY:
        print("WARNING: GROQ_API_KEY is not set!")
        print("Get a free key at https://console.groq.com/keys")
        print("Then set it: $env:GROQ_API_KEY='gsk_your-key-here'")
    else:
        print(f"GROQ_API_KEY loaded (ends with ...{GROQ_API_KEY[-4:]})")
        print(f"Using model: {GROQ_MODEL}")
    if WA_TOKEN and WA_PHONE_ID:
        print(f"WhatsApp connected (Phone ID: {WA_PHONE_ID})")
    else:
        print("WhatsApp not configured - simulated mode only")
        print("Set WA_TOKEN and WA_PHONE_ID for real WhatsApp")
    app.run(debug=True, port=5000)
