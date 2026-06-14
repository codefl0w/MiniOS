import json
import os
import sqlite3
import time
import traceback
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from env_loader import load_env
from flask import Blueprint, Flask, abort, jsonify, redirect, request, send_from_directory, url_for
from werkzeug.utils import secure_filename

load_env()

from settings import app_settings, default_app_setting
from ui import h, phone_page


BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ME_ID = int(os.environ.get("ME_ID", "0"))
PORT = int(os.environ.get("PORT", "2000"))

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "messages.db"))
UPLOAD_DIR = os.path.abspath(os.environ.get("UPLOAD_DIR", os.path.join(BASE_DIR, "uploads")))
os.makedirs(UPLOAD_DIR, exist_ok=True)

RESIZE_IMAGES = os.environ.get("RESIZE_IMAGES", "1") == "1"
MAX_IMAGE_WIDTH = int(os.environ.get("MAX_IMAGE_WIDTH", "800"))
MAX_DOWNLOAD_BYTES = int(os.environ.get("MAX_DOWNLOAD_BYTES", str(8 * 1024 * 1024)))
MAX_SHOW = 10

minigram_bp = Blueprint("minigram", __name__)

EMOJI_MAP = {
    "\U0001f49b": "<3",
    "\u2764\ufe0f": "<3",
    "\U0001f499": "<3",
    "\U0001f49a": "<3",
    "\U0001f49c": "<3",
    "\U0001f642": ":)",
    "\U0001f600": ":D",
    "\U0001f602": ":'D",
    "\U0001f609": ";)",
    "\U0001f618": ":3",
    "\u2639\ufe0f": ":(",
    "\U0001f61b": ":p",
}
ASCII_MAP = {
    "<3": "\U0001f49b",
    ":)": "\U0001f642",
    ":D": "\U0001f600",
    ":'D": "\U0001f602",
    ";)": "\U0001f609",
    ":3": "\U0001f618",
    ":(": "\u2639\ufe0f",
    ":p": "\U0001f61b",
}

MINIGRAM_CSS = """
.row{display:block;border-top:1px solid #263241;padding:8px 0;color:#fff;}
.row strong{color:#fff;}
.small{display:block;color:#91a0af;font-size:11px;margin-top:2px;}
.unread{float:right;color:#fc6b6b;font-weight:bold;padding-left:6px;}
.empty{background:#0f1620;border:1px solid #263241;padding:8px;margin:6px 0;}
.msg{display:block;padding:6px;margin:4px 0;border-radius:7px;box-sizing:border-box;}
.me{background:#3db1ff;color:#000;text-align:right;}
.her{background:#ffc400;color:#000;text-align:left;}
.msg img{max-width:100%;height:auto;display:block;margin-top:5px;border:0;}
.time{font-size:10px;opacity:.78;margin-top:4px;}
form.compose{background:#0f1620;border-top:1px solid #263241;margin:8px -6px -6px;padding:6px;}
input[type=text]{width:72%;box-sizing:border-box;background:#fff;color:#000;border:0;padding:6px;font-size:13px;}
input[type=submit]{width:26%;box-sizing:border-box;background:#95e1ff;color:#000;border:0;padding:6px;font-size:13px;}
"""


def register_minigram_routes(flask_app):
    flask_app.register_blueprint(minigram_bp)


def _log(*args):
    print("[MINIGRAM]", *args)


def emoji_to_ascii(text):
    if not text:
        return text
    for emoji, ascii_text in EMOJI_MAP.items():
        text = text.replace(emoji, ascii_text)
    return text


def ascii_to_emoji(text):
    if not text:
        return text
    for ascii_text, emoji in ASCII_MAP.items():
        text = text.replace(ascii_text, emoji)
    return text


def normalize_contacts(raw_contacts):
    contacts = []
    seen_ids = set()
    if not isinstance(raw_contacts, list):
        return contacts
    for row in raw_contacts:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "")).strip()
        try:
            telegram_id = int(row.get("telegram_id", 0))
        except Exception:
            continue
        if not name or telegram_id <= 0 or telegram_id in seen_ids:
            continue
        contacts.append({"name": name, "telegram_id": telegram_id})
        seen_ids.add(telegram_id)
    return contacts


def minigram_settings():
    current = app_settings("minigram")
    return {
        "contacts": normalize_contacts(current["contacts"]),
        "timezone": str(current["timezone"]).strip() or default_app_setting("minigram", "timezone"),
        "timestamp_format": str(current["timestamp_format"]).strip() or default_app_setting("minigram", "timestamp_format"),
    }


def contacts_by_id():
    return {int(contact["telegram_id"]): contact for contact in minigram_settings()["contacts"]}


def contact_for_id(telegram_id):
    return contacts_by_id().get(int(telegram_id))


def chat_key(telegram_id):
    return str(int(telegram_id))


def get_timezone():
    tz_name = minigram_settings()["timezone"]
    try:
        return ZoneInfo(tz_name)
    except Exception:
        fallback_timezone = default_app_setting("minigram", "timezone")
        try:
            return ZoneInfo(fallback_timezone)
        except Exception:
            return timezone(timedelta(hours=3))


def format_timestamp(ts, full=False):
    fmt = minigram_settings()["timestamp_format"]
    if full or fmt == "full":
        pattern = "%Y-%m-%d %H:%M"
    else:
        pattern = "%d.%m %H:%M"
    return datetime.fromtimestamp(float(ts), timezone.utc).astimezone(get_timezone()).strftime(pattern)


def ensure_db_ready():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL,
                text TEXT,
                photo_url TEXT,
                timestamp REAL NOT NULL,
                chat TEXT,
                is_incoming INTEGER DEFAULT 0,
                is_seen INTEGER DEFAULT 0
            )
            """
        )
        conn.commit()
        c.execute("PRAGMA table_info(messages)")
        cols = [row[1] for row in c.fetchall()]
        if "chat" not in cols:
            c.execute("ALTER TABLE messages ADD COLUMN chat TEXT")
        if "is_incoming" not in cols:
            c.execute("ALTER TABLE messages ADD COLUMN is_incoming INTEGER DEFAULT 0")
        if "is_seen" not in cols:
            c.execute("ALTER TABLE messages ADD COLUMN is_seen INTEGER DEFAULT 0")
        conn.commit()
        conn.close()
    except Exception:
        _log("ensure_db_ready:", traceback.format_exc())


ensure_db_ready()


def connect_db():
    ensure_db_ready()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def save_message_db(sender, text=None, photo_url=None, chat=None, is_incoming=None, is_seen=None):
    if is_incoming is None:
        is_incoming = 0 if sender == "me" else 1
    if is_seen is None:
        is_seen = 0 if is_incoming else 1
    conn = connect_db()
    conn.execute(
        """
        INSERT INTO messages (sender, text, photo_url, timestamp, chat, is_incoming, is_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (sender, text, photo_url, time.time(), str(chat) if chat is not None else None, int(is_incoming), int(is_seen)),
    )
    conn.commit()
    conn.close()


def fetch_last_messages(limit=MAX_SHOW, chat=None):
    conn = connect_db()
    if chat is None:
        rows = conn.execute(
            "SELECT sender, text, photo_url, timestamp FROM messages ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT sender, text, photo_url, timestamp FROM messages WHERE chat=? ORDER BY timestamp DESC LIMIT ?",
            (str(chat), limit),
        ).fetchall()
    conn.close()
    rows.reverse()
    return [dict(row) for row in rows]


def fetch_messages_since(ts, chat=None):
    conn = connect_db()
    if chat is None:
        rows = conn.execute(
            "SELECT sender, text, photo_url, timestamp FROM messages WHERE timestamp > ? ORDER BY timestamp ASC",
            (ts,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT sender, text, photo_url, timestamp FROM messages WHERE chat=? AND timestamp > ? ORDER BY timestamp ASC",
            (str(chat), ts),
        ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def fetch_last_message_preview(chat):
    conn = connect_db()
    row = conn.execute(
        "SELECT sender, text, photo_url, timestamp FROM messages WHERE chat=? ORDER BY timestamp DESC LIMIT 1",
        (str(chat),),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def unread_count(chat):
    conn = connect_db()
    count = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE chat=? AND is_incoming=1 AND is_seen=0",
        (str(chat),),
    ).fetchone()[0]
    conn.close()
    return count


def mark_seen(chat):
    conn = connect_db()
    conn.execute("UPDATE messages SET is_seen=1 WHERE chat=? AND is_incoming=1 AND is_seen=0", (str(chat),))
    conn.commit()
    conn.close()


def get_app_url():
    public_domain = os.environ.get("PYTHONANYWHERE_SITE") or os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    if public_domain:
        return f"https://{public_domain}"
    host = request.headers.get("Host")
    if host:
        scheme = "https" if request.is_secure else "http"
        return f"{scheme}://{host}"
    return "https://example.com"


def send_telegram_message(telegram_id, text):
    if not BOT_TOKEN:
        return False
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        response = requests.post(url, json={"chat_id": int(telegram_id), "text": text}, timeout=10)
        return response.status_code == 200
    except Exception as exc:
        _log("send_telegram_message:", exc)
        return False


def download_telegram_file(file_id):
    if not BOT_TOKEN:
        return None
    try:
        r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getFile", params={"file_id": file_id}, timeout=10)
        r.raise_for_status()
        path = r.json().get("result", {}).get("file_path")
        if not path:
            return None

        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{path}"
        r2 = requests.get(file_url, stream=True, timeout=20)
        r2.raise_for_status()
        content_length = r2.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_DOWNLOAD_BYTES:
            return None

        ext = os.path.splitext(path)[1] or ".jpg"
        filename = secure_filename(f"{file_id}_{int(time.time())}{ext}")
        file_path = os.path.join(UPLOAD_DIR, filename)
        with open(file_path, "wb") as f:
            for chunk in r2.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        if RESIZE_IMAGES:
            try:
                from PIL import Image

                image = Image.open(file_path)
                width, height = image.size
                if width > MAX_IMAGE_WIDTH:
                    new_height = int(MAX_IMAGE_WIDTH * height / width)
                    image = image.resize((MAX_IMAGE_WIDTH, new_height), Image.LANCZOS)
                    image.save(file_path, optimize=True, quality=85)
            except Exception as exc:
                _log("image resize failed:", exc)

        return f"/media/{filename}"
    except Exception as exc:
        _log("download_telegram_file:", exc)
        return None


def admin_enabled():
    load_env(override=True)
    return os.environ.get("MINIGRAM_ENABLE_ADMIN_ROUTES", "0") == "1"


def require_admin_enabled():
    if not admin_enabled():
        abort(404)


@minigram_bp.route("/media/<path:filename>")
def media(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@minigram_bp.route("/contacts")
def contacts():
    contact_rows = minigram_settings()["contacts"]
    body = ""
    if not contact_rows:
        body = (
            "<div class='empty'>No contacts yet.<br>"
            "<a href='/settings/minigram'>Add contacts in Settings</a></div>"
        )
        return phone_page("Minigram", body, nav=[("Apps", "/")], extra_css=MINIGRAM_CSS)

    for contact in contact_rows:
        key = chat_key(contact["telegram_id"])
        preview = fetch_last_message_preview(key)
        preview_text = ""
        preview_time = ""
        if preview:
            preview_text = "[image]" if preview["photo_url"] else (preview["text"] or "")
            if len(preview_text) > 58:
                preview_text = preview_text[:58] + "..."
            preview_time = format_timestamp(preview["timestamp"])
        count = unread_count(key)
        unread_html = f"<span class='unread'>{count}</span>" if count else ""
        body += (
            f"<a class='row' href='/chat/{contact['telegram_id']}'>"
            f"{unread_html}<strong>{h(contact['name'])}</strong>"
            f"<span class='small'>{h(preview_text)} {h(preview_time)}</span></a>"
        )
    return phone_page("Minigram", body, nav=[("Apps", "/")], extra_css=MINIGRAM_CSS)


@minigram_bp.route("/chat/<int:telegram_id>")
def chat(telegram_id):
    contact = contact_for_id(telegram_id)
    if not contact:
        return phone_page("Unknown Contact", "Add this Telegram ID in Settings first.", nav=[("Contacts", "/contacts")]), 404

    key = chat_key(telegram_id)
    mark_seen(key)
    messages = fetch_last_messages(limit=MAX_SHOW, chat=key)
    body = ""
    if not messages:
        body += "<div class='empty'>No messages yet</div>"
    for msg in messages:
        cls = "me" if msg["sender"] == "me" else "her"
        text = h(msg["text"] or "").replace("\n", "<br>")
        image = f"<img src='{h(msg['photo_url'])}' alt=''>" if msg["photo_url"] else ""
        body += f"<div class='msg {cls}'>{text}{image}<div class='time'>{h(format_timestamp(msg['timestamp']))}</div></div>"

    body += f"""
<form class="compose" action="/send" method="post">
<input type="hidden" name="to_id" value="{telegram_id}">
<input type="text" name="msg" autocomplete="off">
<input type="submit" value="Send">
</form>
"""
    nav = [("Apps", "/"), ("Contacts", "/contacts"), ("Refresh", f"/chat/{telegram_id}")]
    return phone_page(contact["name"], body, nav=nav, extra_css=MINIGRAM_CSS)


@minigram_bp.route("/api/messages")
def api_messages():
    try:
        since = float(request.args.get("since", 0))
    except Exception:
        since = 0
    chat_id = request.args.get("chat")
    msgs = fetch_messages_since(since, chat=chat_id)
    return jsonify({"messages": msgs})


@minigram_bp.route("/send", methods=["POST"])
def send():
    raw_msg = request.form.get("msg", "").strip()
    try:
        telegram_id = int(request.form.get("to_id", "0"))
    except Exception:
        telegram_id = 0
    contact = contact_for_id(telegram_id)
    if not contact:
        return redirect(url_for(".contacts"))
    if not raw_msg:
        return redirect(url_for(".chat", telegram_id=telegram_id))

    msg_to_send = ascii_to_emoji(raw_msg)
    success = send_telegram_message(telegram_id, msg_to_send)
    saved_text = raw_msg if success else f"(FAILED TO SEND) {raw_msg}"
    save_message_db("me", text=saved_text, chat=chat_key(telegram_id), is_incoming=0, is_seen=1)
    return redirect(url_for(".chat", telegram_id=telegram_id))


@minigram_bp.route("/webhook/<token>", methods=["GET", "POST"])
def webhook(token):
    if request.method == "GET":
        return "Webhook endpoint"
    if not BOT_TOKEN or token != BOT_TOKEN:
        return "", 403
    try:
        data = request.get_json(force=True)
        msg = (data or {}).get("message")
        if not msg:
            return "", 200

        user_id = int(msg.get("from", {}).get("id", 0))
        if not user_id:
            return "", 200
        key = chat_key(user_id)
        sender = "me" if user_id == ME_ID else "her"
        is_incoming = 0 if sender == "me" else 1
        is_seen = 1 if sender == "me" else 0

        if "text" in msg:
            text = emoji_to_ascii(msg.get("text", "").strip())
            save_message_db(sender, text=text, chat=key, is_incoming=is_incoming, is_seen=is_seen)
            return "", 200

        if "photo" in msg:
            photos = msg.get("photo", [])
            if photos:
                file_id = photos[-1].get("file_id")
                local_path = download_telegram_file(file_id)
                if local_path:
                    text = None if sender == "me" else "sent an image"
                    save_message_db(sender, text=text, photo_url=local_path, chat=key, is_incoming=is_incoming, is_seen=is_seen)
                else:
                    save_message_db(sender, text="[Image download failed]", chat=key, is_incoming=is_incoming, is_seen=is_seen)
            return "", 200

        return "", 200
    except Exception as exc:
        _log("webhook:", exc)
        _log(traceback.format_exc())
        return "", 200


@minigram_bp.route("/set_webhook")
def set_webhook():
    require_admin_enabled()
    try:
        webhook_url = f"{get_app_url()}/webhook/{BOT_TOKEN}"
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook", json={"url": webhook_url}, timeout=10)
        result = r.json()
        if result.get("ok"):
            return phone_page("Webhook", f"Webhook set.<br>{h(webhook_url)}", nav=[("Contacts", "/contacts")])
        return phone_page("Webhook Error", f"<pre>{h(json.dumps(result, indent=2))}</pre>", nav=[("Contacts", "/contacts")])
    except Exception as exc:
        return phone_page("Webhook Error", f"<pre>{h(exc)}</pre>", nav=[("Contacts", "/contacts")]), 500


@minigram_bp.route("/webhook_info")
def webhook_info():
    require_admin_enabled()
    try:
        r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo", timeout=10)
        return jsonify(r.json())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@minigram_bp.route("/debug")
def debug():
    require_admin_enabled()
    conn = connect_db()
    count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    rows = conn.execute(
        """
        SELECT sender, text, photo_url, timestamp, chat, is_incoming, is_seen
        FROM messages ORDER BY timestamp DESC LIMIT 50
        """
    ).fetchall()
    conn.close()
    body = f"<div class='empty'>Stored messages: {count}</div>"
    for row in rows:
        body += (
            "<div class='row'>"
            f"<strong>{h(row['sender'])}</strong> chat={h(row['chat'])}<br>"
            f"{h((row['text'] or '')[:80])} {'[img]' if row['photo_url'] else ''}"
            f"<span class='small'>{h(format_timestamp(row['timestamp'], full=True))} "
            f"seen={row['is_seen']} incoming={row['is_incoming']}</span></div>"
        )
    return phone_page("Minigram Debug", body, nav=[("Contacts", "/contacts")], extra_css=MINIGRAM_CSS)


@minigram_bp.route("/test_images")
def test_images():
    require_admin_enabled()
    try:
        files = os.listdir(UPLOAD_DIR)
        images = [name for name in files if name.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp"))]
        body = f"<div class='empty'>Upload dir: {h(UPLOAD_DIR)}<br>Total files: {len(files)}<br>Images: {len(images)}</div>"
        for image in sorted(images, reverse=True)[:5]:
            path = os.path.join(UPLOAD_DIR, image)
            body += (
                f"<div class='row'><strong>{h(image)}</strong>"
                f"<span class='small'>{os.path.getsize(path)} bytes</span>"
                f"<img src='/media/{h(image)}' alt='' style='max-width:100%;height:auto;border:0;'></div>"
            )
        return phone_page("Image Test", body, nav=[("Contacts", "/contacts"), ("Debug", "/debug")], extra_css=MINIGRAM_CSS)
    except Exception as exc:
        return phone_page("Image Error", f"<pre>{h(exc)}</pre>", nav=[("Contacts", "/contacts")]), 500


if __name__ == "__main__":
    app = Flask(__name__, static_folder=None)
    app.secret_key = os.environ.get("MINIGRAM_SECRET", "change_this_secret")
    register_minigram_routes(app)
    print("Minigram starting...")
    print(f"Listening on 0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
