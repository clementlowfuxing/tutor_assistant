# Tuition Centre Lead Bot

> "Never miss a lead again" — Auto-reply to WhatsApp enquiries, collect student info, and summarise leads automatically.

Built entirely on free-tier services. No credit card required.

---

## What It Does

When a parent messages your WhatsApp number:

1. Bot greets them and answers their enquiry
2. Asks follow-up questions one at a time (student name, form, subject, schedule)
3. Collects all details naturally through conversation
4. Saves a structured lead to `leads.csv`
5. You review leads anytime via the `/leads` endpoint

**Example conversation:**
```
Parent: Hi, do you have maths class for Form 3?
Bot:    Yes we do! Maths is available for Form 1-5, Mon-Sat morning and evening.
        May I know your name?
Parent: I'm Puan Siti
Bot:    Nice to meet you Puan Siti! What is your child's name?
...
```

---

## Architecture

```
Parent's Phone (WhatsApp)
        │
        │  sends message
        ▼
Twilio Sandbox (+1 415 523 8886)     [Free - 5 msg/day]
        │
        │  POST /twilio (webhook)
        ▼
Flask App on PythonAnywhere          [Free hosting]
clement93low.pythonanywhere.com
        │                   │
        │  AI request       │  save lead
        ▼                   ▼
Groq API - Llama 3.1 8B   leads.csv
[Free tier]
        │
        │  AI reply
        ▼
Flask → Twilio API → WhatsApp reply → Parent
```

---

## Infrastructure Services (All Free)

| Service | Purpose | Free Tier Limit |
|---|---|---|
| [Twilio](https://twilio.com) | WhatsApp sandbox — receives and sends messages | 5 outbound messages/day |
| [PythonAnywhere](https://pythonanywhere.com) | Hosts the Flask app 24/7 at a public URL | 1 web app, 512MB storage |
| [Groq](https://console.groq.com) | Runs Llama 3.1 8B AI model via API | 14,400 requests/day |
| [GitHub](https://github.com) | Source code hosting, used to deploy updates | Unlimited public repos |

**Total monthly cost: $0**

---

## Tech Stack

- Python 3.10
- Flask (web framework)
- Groq API with Llama 3.1 8B (AI model)
- Twilio WhatsApp Sandbox (messaging)
- CSV (lead storage, no database needed)

---

## Project Structure

```
tutor_assistant/
├── app.py              # Main Flask app — all routes and AI logic
├── wsgi.py             # WSGI entry point for PythonAnywhere
├── requirements.txt    # Python dependencies
├── templates/
│   └── chat.html       # Browser-based WhatsApp UI for local demo
├── test_chat.py        # Script to simulate a conversation locally
├── leads.csv           # Auto-generated — stores captured leads
├── .env.example        # Environment variable template
└── .gitignore
```

---

## Step-by-Step Setup Guide

### Prerequisites
- Python 3.10+
- Git
- A free account on: GitHub, Groq, Twilio, PythonAnywhere

---

### 1. Get a Groq API Key (Free)

1. Sign up at https://console.groq.com
2. Go to API Keys → Create API Key
3. Copy the key (starts with `gsk_`)

---

### 2. Set Up Twilio WhatsApp Sandbox (Free)

1. Sign up at https://twilio.com (no credit card needed for sandbox)
2. Go to Console → Messaging → Try it out → Send a WhatsApp message
3. Note your **Account SID** and **Auth Token** from the main dashboard
4. On your phone, open WhatsApp and send the join code shown on screen to `+1 415 523 8886`
   - Example: `join example-word`
5. You'll receive a confirmation — your phone is now connected to the sandbox

> **Note:** Twilio free sandbox allows 5 outbound messages per day. Limit resets at UTC midnight.

---

### 3. Clone and Configure Locally

```bash
git clone https://github.com/clementlowfuxing/tutor_assistant.git
cd tutor_assistant
pip install -r requirements.txt
```

Create your `.env` file:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
GROQ_API_KEY=gsk_your-key-here
GROQ_MODEL=llama-3.1-8b-instant

TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your-auth-token-here
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# Set to false if running behind a corporate proxy (e.g. Zscaler)
SSL_VERIFY=true
```

---

### 4. Run Locally (Browser Demo)

```bash
python app.py
```

Open http://localhost:5000 — you'll see a WhatsApp-style chat UI. Type messages as a parent would and the bot will reply in real-time.

Check captured leads at http://localhost:5000/leads

> **Corporate network (Zscaler)?** Set `SSL_VERIFY=false` in your `.env` before running.

---

### 5. Deploy to PythonAnywhere (Free Hosting)

**Sign up** at https://pythonanywhere.com (no credit card required)

**Upload code via Bash console:**

```bash
git clone https://github.com/clementlowfuxing/tutor_assistant.git
cd tutor_assistant
python3.10 -m pip install --user -r requirements.txt
```

**Create `.env` on PythonAnywhere:**

```bash
nano /home/yourusername/tutor_assistant/.env
```

Paste your credentials, save with `Ctrl+X → Y → Enter`.

**Configure the web app:**

1. Go to Web tab → Add a new web app → Manual configuration → Python 3.10
2. Set Source code path: `/home/yourusername/tutor_assistant`
3. Click the WSGI configuration file link and replace its entire contents with:

```python
import sys
import os
from dotenv import load_dotenv

project_home = '/home/yourusername/tutor_assistant'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

load_dotenv(os.path.join(project_home, '.env'))

from app import app as application
```

4. Replace `yourusername` with your actual PythonAnywhere username
5. Click **Reload** on the Web tab

Your app is now live at `https://yourusername.pythonanywhere.com`

---

### 6. Connect Twilio Webhook

1. Go to Twilio Console → Messaging → Try it out → Send a WhatsApp message → Sandbox settings
2. Set **"When a message comes in"** to:
   ```
   https://yourusername.pythonanywhere.com/twilio
   ```
3. Method: `HTTP POST`
4. Save

Send a WhatsApp message to `+1 415 523 8886` — the bot will auto-reply.

---

### 7. Deploying Updates

Whenever you update the code locally:

```bash
git add .
git commit -m "your update message"
git push
```

Then on PythonAnywhere Bash console:

```bash
cd /home/yourusername/tutor_assistant
git fetch origin && git reset --hard origin/main
```

Reload on the Web tab.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Browser chat UI (WhatsApp simulation) |
| POST | `/webhook` | Simulated webhook for local testing |
| POST | `/twilio` | Real WhatsApp webhook (called by Twilio) |
| GET | `/leads` | View all captured leads as JSON |

---

## Changing the AI Model

Edit `GROQ_MODEL` in your `.env`:

```env
GROQ_MODEL=llama-3.1-8b-instant      # Fast (default)
GROQ_MODEL=llama-3.3-70b-versatile   # Smarter, slower
GROQ_MODEL=mixtral-8x7b-32768        # Good for long conversations
GROQ_MODEL=gemma2-9b-it              # Google's model
```

---

## Monitoring Logs (PythonAnywhere)

```bash
# Live request log
tail -f /var/log/yourusername.pythonanywhere.com.access.log

# App logs (print statements, errors)
tail -f /var/log/yourusername.pythonanywhere.com.server.log

# Error log
tail -f /var/log/yourusername.pythonanywhere.com.error.log
```

---

## Known Limitations (Free Tier)

| Limitation | Cause | Solution |
|---|---|---|
| 5 WhatsApp replies/day | Twilio sandbox limit | Add Twilio credit (~$15) to remove limit |
| App may sleep after inactivity | PythonAnywhere free tier | First message after idle may be slow |
| Conversations reset on restart | In-memory storage | Add a database (e.g. SQLite) for persistence |
| leads.csv resets on redeploy | File stored on server disk | Export CSV regularly or use a database |

---

## Future Improvements

- Replace CSV with SQLite or Google Sheets for persistent lead storage
- Add a simple admin dashboard to view and manage leads
- Upgrade to Meta WhatsApp Business API for production use (no message limits)
- Add multi-language support (Bahasa Malaysia / English)
