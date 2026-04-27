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

# Twilio WhatsApp config
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

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


def send_whatsapp_reply(to_phone, message):
    """Send a reply back via Twilio WhatsApp."""
    http_requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json",
        auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
        data={
            "From": TWILIO_WHATSAPP_NUMBER,
            "To": to_phone,
            "Body": message,
        },
    )


# --- Routes ---

@app.route("/twilio", methods=["POST"])
def twilio_webhook():
    """Receive real WhatsApp messages via Twilio and auto-reply."""
    phone = request.form.get("From", "")
    message = request.form.get("Body", "")

    if not message:
        return "<Response></Response>", 200

    phone_clean = phone.replace("whatsapp:", "")
    print(f"WhatsApp from {phone_clean}: {message}")

    try:
        reply, extracted = chat_with_ai(phone_clean, message)
        send_whatsapp_reply(phone, reply)
        print(f"Replied to {phone_clean}: {reply[:80]}...")
        if extracted and extracted.get("complete"):
            print(f"Lead captured for {phone_clean}!")
    except Exception as e:
        print(f"Error: {e}")

    return "<Response></Response>", 200

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
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
        print(f"Twilio WhatsApp ready (sandbox: {TWILIO_WHATSAPP_NUMBER})")
    else:
        print("Twilio not configured - set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN")
    app.run(debug=True, port=5000)
