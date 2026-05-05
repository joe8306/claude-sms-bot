"""
Claude SMS bot - Twilio webhook that talks to Claude.

Setup (see SETUP.txt):
  1. pip install -r requirements.txt
  2. copy .env.example to .env and fill in keys
  3. py -3 bot.py        (runs Flask on http://localhost:5000)
  4. ngrok http 5000     (in another terminal - exposes it publicly)
  5. paste the ngrok URL + /sms into your Twilio number's "A MESSAGE COMES IN" webhook
"""
import os
import json
import time
from pathlib import Path
from flask import Flask, request, abort
from anthropic import Anthropic
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
anthropic = Anthropic()  # reads ANTHROPIC_API_KEY from .env
validator = RequestValidator(os.environ["TWILIO_AUTH_TOKEN"])

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024
SYSTEM_PROMPT = (
    "You are Chaim's personal assistant, replying over SMS. "
    "Keep replies under 1500 characters and skip filler. "
    "If a question needs a long answer, summarize and offer to continue."
)

# Persist conversations on Fly volume if mounted at /data, else local folder
DATA_DIR = Path("/data") if Path("/data").is_dir() else Path(__file__).parent
HISTORY_FILE = DATA_DIR / "conversations.json"
MAX_TURNS = 40  # keep last 20 user + 20 assistant messages per number


def load_history():
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return {}


def save_history(data):
    HISTORY_FILE.write_text(json.dumps(data, indent=2))


@app.route("/sms", methods=["POST"])
def sms_reply():
    # 1. Verify the request actually came from Twilio
    signature = request.headers.get("X-Twilio-Signature", "")
    if not validator.validate(request.url, request.form, signature):
        print(f"[{time.strftime('%H:%M:%S')}] rejected: bad signature")
        abort(403)

    from_number = request.form.get("From", "")
    body = request.form.get("Body", "").strip()
    print(f"[{time.strftime('%H:%M:%S')}] {from_number}: {body!r}")

    # 2. Load history, append new user message
    all_convos = load_history()
    history = all_convos.get(from_number, [])
    history.append({"role": "user", "content": body})

    # 3. Call Claude
    try:
        msg = anthropic.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=history,
        )
        reply_text = msg.content[0].text.strip()
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] claude error: {e}")
        reply_text = f"(error talking to Claude: {e})"

    # 4. Save updated history
    history.append({"role": "assistant", "content": reply_text})
    all_convos[from_number] = history[-MAX_TURNS:]
    save_history(all_convos)

    print(f"[{time.strftime('%H:%M:%S')}] -> {reply_text[:80]!r}")

    # 5. Return TwiML so Twilio sends it as the SMS reply
    resp = MessagingResponse()
    resp.message(reply_text[:1500])
    return str(resp), 200, {"Content-Type": "application/xml"}


@app.route("/reset", methods=["POST"])
def reset():
    """Wipe conversation history. POST with form field 'From' or wipe everyone."""
    from_number = request.form.get("From")
    all_convos = load_history()
    if from_number:
        all_convos.pop(from_number, None)
    else:
        all_convos = {}
    save_history(all_convos)
    return "ok"


@app.route("/health")
def health():
    return "ok"


if __name__ == "__main__":
    print("Claude SMS bot starting on http://localhost:5000")
    print("Webhook endpoint: POST /sms")
    app.run(host="0.0.0.0", port=5000, debug=False)
