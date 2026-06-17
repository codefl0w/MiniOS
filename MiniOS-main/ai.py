import os
import sqlite3
import time
from datetime import datetime

import requests
from env_loader import load_env
from flask import redirect, request
from ui import h, phone_page

load_env()

BASE_DIR = os.path.dirname(__file__)
AI_DB_PATH = os.environ.get("AI_DB_PATH", os.path.join(BASE_DIR, "ai.db"))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_CONTEXT_MESSAGES = 12

SYSTEM_PROMPT = (
    "You are a concise assistant for a 240x320 feature phone browser. "
    "Answer in plain text. Keep replies short unless user asks for detail. "
    "Avoid tables. Use compact bullets only when useful."
)


def connect_db():
    conn = sqlite3.connect(AI_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_ai_db():
    conn = connect_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            text TEXT NOT NULL,
            timestamp REAL NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def save_message(role, text):
    conn = connect_db()
    conn.execute(
        "INSERT INTO ai_messages (role, text, timestamp) VALUES (?, ?, ?)",
        (role, text, time.time()),
    )
    conn.commit()
    conn.close()


def fetch_messages(limit=MAX_CONTEXT_MESSAGES):
    conn = connect_db()
    rows = conn.execute(
        "SELECT role, text, timestamp FROM ai_messages ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return list(reversed(rows))


def clear_messages():
    conn = connect_db()
    conn.execute("DELETE FROM ai_messages")
    conn.commit()
    conn.close()


def format_time(ts):
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def text_html(text):
    return h(text).replace("\n", "<br>")


def build_gemini_contents(rows):
    contents = []
    for row in rows:
        role = "model" if row["role"] == "ai" else "user"
        contents.append({"role": role, "parts": [{"text": row["text"]}]})
    return contents


def extract_reply(data):
    candidates = data.get("candidates") or []
    if not candidates:
        return "No response."
    parts = candidates[0].get("content", {}).get("parts", [])
    texts = [part.get("text", "") for part in parts if part.get("text")]
    if texts:
        return "\n".join(texts).strip()
    finish = candidates[0].get("finishReason")
    if finish:
        return f"No text response. Finish: {finish}"
    return "No text response."


def ask_gemini(rows):
    if not GEMINI_API_KEY:
        return "Gemini API key missing. Set GEMINI_API_KEY in .env."

    url = GEMINI_URL.format(model=GEMINI_MODEL)
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": build_gemini_contents(rows),
        "generationConfig": {
            "temperature": 0.6,
            "maxOutputTokens": 512,
        },
    }
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=35)
        if resp.status_code != 200:
            try:
                detail = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                detail = resp.text
            return f"Gemini error {resp.status_code}: {detail[:300]}"
        return extract_reply(resp.json())
    except requests.Timeout:
        return "Gemini request timed out."
    except requests.RequestException as exc:
        return f"Gemini network error: {exc}"
    except Exception as exc:
        return f"AI error: {exc}"


def render_ai_chat(rows):
    html = """
<html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{font-family:Arial;background:#191f2e;color:#fff;margin:0;padding:0;font-size:12px;}
.topbar{padding:8px;background:#0f1620;}
.wrap{padding:4px 4px 44px;}
.msg{display:block;width:100%;padding:6px;margin:4px 0;border-radius:10px;box-sizing:border-box;}
.me{background:#3db1ff;color:#000;text-align:right;}
.ai{background:#ffc400;color:#000;text-align:left;}
.time{font-size:10px;opacity:0.8;margin-top:4px;}
form.send{position:fixed;bottom:0;left:0;right:0;background:#111;padding:6px;}
input[type=text]{width:74%;padding:6px;font-size:12px;background:#ffffff;border:none;box-sizing:border-box;}
input[type=submit]{width:24%;padding:6px;font-size:12px;background:#95e1ff;border:none;box-sizing:border-box;}
a.back{color:#9fdfff;text-decoration:none;}
</style>
<script>window.onload=function(){window.scrollTo(0,document.body.scrollHeight);};</script>
</head><body><div class='topbar'><a class='back' href='/'>Apps</a> | <a class='back' href='/ai/clear'>Clear</a> <strong> - AI</strong></div>
<div class="wrap">
"""
    if not rows:
        html += "<div style='padding:8px;color:#999;'>Ask something</div>"
    for row in rows:
        cls = "me" if row["role"] == "user" else "ai"
        html += f"<div class='msg {cls}'>{text_html(row['text'])}<div class='time'>{format_time(row['timestamp'])}</div></div>"
    html += """
</div><form class="send" action="/ai/send" method="post">
<input type="text" name="msg" autocomplete="off">
<input type="submit" value="Ask">
</form></body></html>
"""
    return html


def register_ai_routes(flask_app, prefix="/ai"):
    init_ai_db()
    base = prefix.rstrip("/")

    @flask_app.route(base)
    @flask_app.route(base + "/")
    def ai_index():
        return render_ai_chat(fetch_messages(limit=50))

    @flask_app.route(base + "/send", methods=["POST"])
    def ai_send():
        msg = request.form.get("msg", "").strip()
        if not msg:
            return redirect(base)
        save_message("user", msg)
        rows = fetch_messages()
        reply = ask_gemini(rows)
        save_message("ai", reply)
        return redirect(base)

    @flask_app.route(base + "/clear", methods=["GET", "POST"])
    def ai_clear():
        if request.method == "GET":
            body = f"""
<p>This deletes AI chat history.</p>
<form method="post" action="{base}/clear">
<input type="submit" value="Clear">
</form>
"""
            css = "input[type=submit]{background:#ff8b8b;color:#000;border:0;padding:6px 8px;font-size:13px;}"
            return phone_page("Clear AI", body, nav=[("Apps", "/"), ("AI", base)], extra_css=css)
        clear_messages()
        return redirect(base)
