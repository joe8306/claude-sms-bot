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
from flask import Flask, request, abort, jsonify
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


# ---- Browser chat (test interface, no SMS needed) ---------------------------
# Lives at /chat. Uses a separate conversation key so it doesn't mix with the
# SMS history. No auth - URL is just non-obvious. Burns Anthropic credits if
# someone finds it, so don't share the URL.

CHAT_HTML = """<!doctype html>
<html><head><meta charset="utf-8">
<title>Claude bot</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#1a1a1a;color:#eee;height:100vh;display:flex;flex-direction:column}
  header{padding:12px 16px;background:#222;border-bottom:1px solid #333;font-weight:600;font-size:14px;display:flex;justify-content:space-between;align-items:center}
  header button{background:#444;color:#eee;border:0;padding:6px 12px;border-radius:6px;cursor:pointer;font-size:12px}
  #log{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px}
  .msg{max-width:75%;padding:10px 14px;border-radius:14px;line-height:1.4;white-space:pre-wrap;word-wrap:break-word}
  .user{align-self:flex-end;background:#0b6cff;color:#fff}
  .bot{align-self:flex-start;background:#2d2d2d}
  .err{align-self:center;background:#502020;font-size:12px;padding:6px 10px}
  form{display:flex;padding:12px;gap:8px;border-top:1px solid #333;background:#222;align-items:center}
  input{flex:1;padding:10px 14px;border-radius:20px;border:0;background:#333;color:#eee;font-size:14px;outline:none}
  #mic{background:#444;color:#fff;border:0;width:44px;height:44px;border-radius:50%;cursor:pointer;font-size:18px;flex-shrink:0;display:flex;align-items:center;justify-content:center;padding:0}
  #mic:hover{background:#555}
  #mic.recording{background:#e74c3c;animation:pulse 1.2s ease-in-out infinite}
  @keyframes pulse{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(1.08);opacity:.85}}
  button[type=submit]{background:#0b6cff;color:#fff;border:0;padding:10px 18px;border-radius:20px;cursor:pointer;font-weight:600}
  button[type=submit]:disabled{opacity:.5;cursor:not-allowed}
  .typing{font-style:italic;opacity:.6}
  .hint{font-size:11px;color:#888;text-align:center;padding:4px}
</style></head>
<body>
<header><span>Claude bot</span><button onclick="reset()">Clear</button></header>
<div id="log"></div>
<div class="hint" id="hint"></div>
<form id="f">
  <input id="i" placeholder="Type or tap mic to speak..." autocomplete="off" autofocus>
  <button type="button" id="mic" title="Hold to dictate">🎤</button>
  <button type="submit">Send</button>
</form>
<script>
const log = document.getElementById('log');
const form = document.getElementById('f');
const input = document.getElementById('i');
const sendBtn = form.querySelector('button[type=submit]');
const micBtn = document.getElementById('mic');
const hint = document.getElementById('hint');

function add(role, text) {
  const d = document.createElement('div');
  d.className = 'msg ' + role;
  d.textContent = text;
  log.appendChild(d);
  log.scrollTop = log.scrollHeight;
  return d;
}

async function reset() {
  await fetch('/chat/reset', {method:'POST'});
  log.innerHTML = '';
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  add('user', text);
  input.value = '';
  sendBtn.disabled = true;
  const typing = add('bot typing', '...');
  try {
    const r = await fetch('/chat/api', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text})
    });
    const data = await r.json();
    typing.remove();
    if (data.error) add('err', data.error);
    else add('bot', data.reply);
  } catch (err) {
    typing.remove();
    add('err', 'Network error: ' + err.message);
  }
  sendBtn.disabled = false;
  input.focus();
});

// ---- Voice-to-text (browser Web Speech API) ----
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
if (!SR) {
  micBtn.style.display = 'none';
  hint.textContent = '(voice input not supported in this browser - use Chrome/Edge/Safari)';
} else {
  const recog = new SR();
  recog.continuous = true;
  recog.interimResults = true;
  recog.lang = 'en-US';

  let listening = false;
  let baseText = '';

  micBtn.addEventListener('click', () => {
    if (listening) {
      recog.stop();
    } else {
      baseText = input.value ? input.value + ' ' : '';
      try { recog.start(); } catch (e) { /* already started */ }
    }
  });

  recog.onstart = () => {
    listening = true;
    micBtn.classList.add('recording');
    hint.textContent = 'Listening... tap mic again to stop';
  };

  recog.onend = () => {
    listening = false;
    micBtn.classList.remove('recording');
    hint.textContent = '';
    input.focus();
  };

  recog.onerror = (e) => {
    listening = false;
    micBtn.classList.remove('recording');
    if (e.error === 'not-allowed') {
      hint.textContent = 'Microphone permission denied. Allow it in your browser settings.';
    } else if (e.error === 'no-speech') {
      hint.textContent = '';
    } else {
      hint.textContent = 'Mic error: ' + e.error;
    }
  };

  recog.onresult = (e) => {
    let interim = '';
    let finalText = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const t = e.results[i][0].transcript;
      if (e.results[i].isFinal) finalText += t;
      else interim += t;
    }
    input.value = (baseText + finalText + interim).trim();
  };
}
</script></body></html>"""

BROWSER_KEY = "_browser_chat"


@app.route("/chat")
def chat_page():
    return CHAT_HTML, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/chat/api", methods=["POST"])
def chat_api():
    data = request.get_json(silent=True) or {}
    body = (data.get("message") or "").strip()
    if not body:
        return jsonify(error="empty message"), 400

    all_convos = load_history()
    history = all_convos.get(BROWSER_KEY, [])
    history.append({"role": "user", "content": body})

    try:
        msg = anthropic.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=history,
        )
        reply = msg.content[0].text.strip()
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] /chat error: {e}")
        return jsonify(error=f"Claude error: {e}"), 500

    history.append({"role": "assistant", "content": reply})
    all_convos[BROWSER_KEY] = history[-MAX_TURNS:]
    save_history(all_convos)
    return jsonify(reply=reply)


@app.route("/chat/reset", methods=["POST"])
def chat_reset():
    all_convos = load_history()
    all_convos.pop(BROWSER_KEY, None)
    save_history(all_convos)
    return jsonify(ok=True)


if __name__ == "__main__":
    print("Claude SMS bot starting on http://localhost:5000")
    print("Webhook endpoint: POST /sms")
    app.run(host="0.0.0.0", port=5000, debug=False)
