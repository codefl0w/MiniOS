import imaplib
import os
import re
import smtplib
import time
from datetime import datetime
from email import message_from_bytes
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser

from env_loader import load_env
from flask import redirect, request

load_env()

from settings import app_settings
from ui import h, phone_page

IMAP_HOST = os.environ.get("MAIL_IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.environ.get("MAIL_IMAP_PORT", "993"))
SMTP_HOST = os.environ.get("MAIL_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("MAIL_SMTP_PORT", "465"))
MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
MAIL_FROM = os.environ.get("MAIL_FROM", MAIL_USERNAME)
MAIL_BODY_LIMIT = int(os.environ.get("MAIL_BODY_LIMIT", "12000"))

_inbox_cache = {"ts": 0, "rows": [], "error": ""}
_message_cache = {}


def mail_limit():
    return int(app_settings("mail").get("limit", 40))


def mail_cache_ttl():
    return int(app_settings("mail").get("cache_ttl", 600))


class HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "p", "div", "li", "tr"):
            self.parts.append("\n")

    def handle_data(self, data):
        if data:
            self.parts.append(data)

    def text(self):
        text = "".join(self.parts)
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
        return text.strip()


def decode_value(value):
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def short_sender(value):
    name, addr = parseaddr(decode_value(value))
    return name or addr or value or "(unknown)"


def format_date(value):
    if not value:
        return ""
    try:
        dt = parsedate_to_datetime(value)
        return dt.astimezone().strftime("%d.%m %H:%M")
    except Exception:
        return value[:16]


def cache_age(ts):
    if not ts:
        return "none"
    age = max(0, int(time.time() - ts))
    if age < 60:
        return f"{age}s"
    return f"{age // 60}m {age % 60}s"


def require_config():
    missing = []
    if not MAIL_USERNAME:
        missing.append("MAIL_USERNAME")
    if not MAIL_PASSWORD:
        missing.append("MAIL_PASSWORD")
    return missing


def connect_imap():
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    imap.login(MAIL_USERNAME, MAIL_PASSWORD)
    imap.select("INBOX", readonly=True)
    return imap


def first_bytes(fetch_data):
    for item in fetch_data:
        if isinstance(item, tuple) and isinstance(item[1], bytes):
            return item[1]
    return b""


def fetch_inbox(force=False):
    now = time.time()
    if not force and _inbox_cache["rows"] and now - _inbox_cache["ts"] < mail_cache_ttl():
        return _inbox_cache

    missing = require_config()
    if missing:
        return {"ts": now, "rows": [], "error": "Missing " + ", ".join(missing)}

    rows = []
    try:
        imap = connect_imap()
        typ, data = imap.uid("search", None, "ALL")
        if typ != "OK":
            raise RuntimeError("IMAP search failed")
        uids = data[0].split()[-mail_limit():][::-1]
        for uid in uids:
            uid_text = uid.decode("ascii", "ignore")
            typ, fetched = imap.uid("fetch", uid, "(BODY.PEEK[])")
            if typ != "OK":
                continue
            msg = message_from_bytes(first_bytes(fetched))
            body, attachments, trimmed = extract_body(msg)
            message_data = {
                "from": decode_value(msg.get("From", "")),
                "to": decode_value(msg.get("To", "")),
                "subject": decode_value(msg.get("Subject", "(no subject)")),
                "date": format_date(msg.get("Date", "")),
                "body": body,
                "attachments": attachments,
                "trimmed": trimmed,
                "cache_ts": now,
            }
            _message_cache[uid_text] = {"ts": now, "msg": message_data}
            rows.append(
                {
                    "uid": uid_text,
                    "from": short_sender(msg.get("From", "")),
                    "subject": decode_value(msg.get("Subject", "(no subject)")),
                    "date": format_date(msg.get("Date", "")),
                }
            )
        imap.logout()
        _inbox_cache.update({"ts": now, "rows": rows, "error": ""})
    except Exception as exc:
        if _inbox_cache["rows"]:
            _inbox_cache["error"] = str(exc)
        else:
            _inbox_cache.update({"ts": now, "rows": rows, "error": str(exc)})
    return _inbox_cache


def html_to_text(html):
    parser = HTMLText()
    parser.feed(html or "")
    return parser.text()


def decode_part(part):
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, "replace")


def extract_body(msg):
    text_parts = []
    html_parts = []
    attachments = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = (part.get("Content-Disposition") or "").lower()
            filename = part.get_filename()
            if filename:
                attachments.append(decode_value(filename))
            if "attachment" in disposition:
                continue
            if content_type == "text/plain":
                text_parts.append(decode_part(part))
            elif content_type == "text/html":
                html_parts.append(html_to_text(decode_part(part)))
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            text_parts.append(decode_part(msg))
        elif content_type == "text/html":
            html_parts.append(html_to_text(decode_part(msg)))

    body = "\n\n".join(part.strip() for part in text_parts if part.strip())
    if not body:
        body = "\n\n".join(part.strip() for part in html_parts if part.strip())
    body = body.strip() or "(empty message)"
    trimmed = False
    if len(body) > MAIL_BODY_LIMIT:
        body = body[:MAIL_BODY_LIMIT] + "\n\n[trimmed]"
        trimmed = True
    return body, attachments, trimmed


def fetch_message(uid):
    if not uid.isdigit():
        raise ValueError("Bad UID")
    cached = _message_cache.get(uid)
    if cached and time.time() - cached["ts"] < mail_cache_ttl():
        msg = dict(cached["msg"])
        msg["cache_ts"] = cached["ts"]
        return msg
    imap = connect_imap()
    typ, fetched = imap.uid("fetch", uid.encode("ascii"), "(BODY.PEEK[])")
    imap.logout()
    if typ != "OK":
        raise RuntimeError("IMAP fetch failed")
    msg = message_from_bytes(first_bytes(fetched))
    body, attachments, trimmed = extract_body(msg)
    result = {
        "from": decode_value(msg.get("From", "")),
        "to": decode_value(msg.get("To", "")),
        "subject": decode_value(msg.get("Subject", "(no subject)")),
        "date": format_date(msg.get("Date", "")),
        "body": body,
        "attachments": attachments,
        "trimmed": trimmed,
        "cache_ts": time.time(),
    }
    _message_cache[uid] = {"ts": result["cache_ts"], "msg": result}
    return result


def send_mail(to_addr, subject, body):
    missing = require_config()
    if missing:
        raise RuntimeError("Missing " + ", ".join(missing))
    msg = EmailMessage()
    msg["From"] = MAIL_FROM or MAIL_USERNAME
    msg["To"] = to_addr
    msg["Subject"] = subject or "(no subject)"
    msg.set_content(body or "")
    smtp = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30)
    try:
        smtp.login(MAIL_USERNAME, MAIL_PASSWORD)
        smtp.send_message(msg)
    finally:
        smtp.quit()


MAIL_CSS = """
.row{display:block;border-top:1px solid #263241;padding:7px 0;color:#fff;}
.from{display:block;color:#ffd35a;font-size:12px;}
.subj{display:block;color:#fff;font-size:12px;line-height:1.15;}
.small{display:block;color:#91a0af;font-size:11px;margin-top:2px;}
.err{color:#ff8b8b;font-size:12px;}
.body{background:#0f1620;border:1px solid #263241;padding:6px;margin:6px 0;white-space:normal;}
form{margin:0;}
input[type=text],textarea{width:100%;box-sizing:border-box;background:#fff;color:#000;border:0;padding:6px;font-size:13px;margin:0 0 4px;font-family:Arial;}
textarea{height:132px;}
input[type=submit]{background:#95e1ff;color:#000;border:0;padding:6px 8px;font-size:13px;}
"""


def text_html(text):
    return h(text).replace("\n", "<br>")


def config_help(error):
    return f"""
<p class="err">{h(error)}</p>
<p class="small">Use Gmail app password. Set env vars:</p>
<div class="body">MAIL_USERNAME<br>MAIL_PASSWORD<br>MAIL_FROM optional</div>
"""


def register_mail_routes(flask_app, prefix="/mail"):
    base = prefix.rstrip("/")

    @flask_app.route(base)
    @flask_app.route(base + "/")
    def mail_index():
        force = request.args.get("refresh") == "1"
        inbox = fetch_inbox(force=force)
        body = f"<p><a href='{base}/compose'>Compose</a> | <a href='{base}?refresh=1'>Refresh</a></p>"
        body += f"<div class='small'>Cache age: {h(cache_age(inbox['ts']))} | TTL {h(mail_cache_ttl())}s</div>"
        if inbox["error"]:
            body += config_help(inbox["error"])
        if not inbox["rows"]:
            body += "<p class='small'>No messages</p>"
        for row in inbox["rows"]:
            body += (
                f"<a class='row' href='{base}/msg/{h(row['uid'])}'>"
                f"<span class='from'>{h(row['from'])}</span>"
                f"<span class='subj'>{h(row['subject'])}</span>"
                f"<span class='small'>{h(row['date'])}</span></a>"
            )
        return phone_page("Mail", body, nav=[("Apps", "/")], extra_css=MAIL_CSS)

    @flask_app.route(base + "/msg/<uid>")
    def mail_message(uid):
        try:
            msg = fetch_message(uid)
        except Exception as exc:
            return phone_page("Mail Error", config_help(str(exc)), nav=[("Apps", "/"), ("Mail", base)], extra_css=MAIL_CSS), 500
        body = f"""
<div class="small">From: {h(msg["from"])}</div>
<div class="small">To: {h(msg["to"])}</div>
<div class="small">Date: {h(msg["date"])}</div>
<div class="small">Cache age: {h(cache_age(msg.get("cache_ts", 0)))}</div>
<h3>{h(msg["subject"])}</h3>
<div class="body">{text_html(msg["body"])}</div>
"""
        if msg["attachments"]:
            body += f"<div class='small'>Attachments skipped: {h(', '.join(msg['attachments']))}</div>"
        return phone_page("Mail", body, nav=[("Apps", "/"), ("Inbox", base)], extra_css=MAIL_CSS)

    @flask_app.route(base + "/compose", methods=["GET", "POST"])
    def mail_compose():
        error = ""
        sent = False
        to_addr = request.form.get("to", "").strip()
        subject = request.form.get("subject", "").strip()
        body_text = request.form.get("body", "").strip()
        if request.method == "POST":
            if "@" not in to_addr or not body_text:
                error = "Bad recipient or empty body"
            else:
                try:
                    send_mail(to_addr, subject, body_text)
                    sent = True
                except Exception as exc:
                    error = str(exc)
        if sent:
            body = f"<p>Sent.</p><p><a href='{base}'>Inbox</a></p>"
        else:
            body = ""
            if error:
                body += f"<p class='err'>{h(error)}</p>"
            body += f"""
<form method="post" action="{base}/compose">
<input type="text" name="to" value="{h(to_addr)}" placeholder="To">
<input type="text" name="subject" value="{h(subject)}" placeholder="Subject">
<textarea name="body">{h(body_text)}</textarea>
<input type="submit" value="Send">
</form>
"""
        return phone_page("Compose", body, nav=[("Apps", "/"), ("Inbox", base)], extra_css=MAIL_CSS)
