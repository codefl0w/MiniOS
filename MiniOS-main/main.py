import base64
import os
from html import escape as html_escape

from env_loader import load_env
from flask import Flask, make_response, send_from_directory
from werkzeug.utils import secure_filename

load_env()

from minigram import PORT, register_minigram_routes
from ui import app_drawer, phone_page

try:
    from ai import register_ai_routes
    AI_IMPORT_ERROR = None
except Exception as exc:
    register_ai_routes = None
    AI_IMPORT_ERROR = exc

try:
    from boards import register_boards_routes
    BOARDS_IMPORT_ERROR = None
except Exception as exc:
    register_boards_routes = None
    BOARDS_IMPORT_ERROR = exc

try:
    from finance import register_finance_routes
    FINANCE_IMPORT_ERROR = None
except Exception as exc:
    register_finance_routes = None
    FINANCE_IMPORT_ERROR = exc

try:
    from mail import register_mail_routes
    MAIL_IMPORT_ERROR = None
except Exception as exc:
    register_mail_routes = None
    MAIL_IMPORT_ERROR = exc

try:
    from news import register_news_routes
    NEWS_IMPORT_ERROR = None
except Exception as exc:
    register_news_routes = None
    NEWS_IMPORT_ERROR = exc

try:
    from notes import register_notes_routes
    NOTES_IMPORT_ERROR = None
except Exception as exc:
    register_notes_routes = None
    NOTES_IMPORT_ERROR = exc

try:
    from settings import register_settings_routes
    SETTINGS_IMPORT_ERROR = None
except Exception as exc:
    register_settings_routes = None
    SETTINGS_IMPORT_ERROR = exc

try:
    from weather import register_weather_routes
    WEATHER_IMPORT_ERROR = None
except Exception as exc:
    register_weather_routes = None
    WEATHER_IMPORT_ERROR = exc

try:
    from youtubewap import register_youtubewap_routes
    YOUTUBEWAP_IMPORT_ERROR = None
except Exception as exc:
    register_youtubewap_routes = None
    YOUTUBEWAP_IMPORT_ERROR = exc

BASE_DIR = os.path.dirname(__file__)
ICONS_DIR = os.path.abspath(os.environ.get("ICONS_DIR", os.path.join(BASE_DIR, "icons")))
os.makedirs(ICONS_DIR, exist_ok=True)
BLANK_ICON = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)

app = Flask(__name__, static_folder=None)
app.secret_key = os.environ.get("MINIGRAM_SECRET", "change_this_secret")
application = app

register_minigram_routes(app)
if register_ai_routes:
    register_ai_routes(app, "/ai")
if register_boards_routes:
    register_boards_routes(app, "/boards")
if register_finance_routes:
    register_finance_routes(app, "/finance")
if register_mail_routes:
    register_mail_routes(app, "/mail")
if register_news_routes:
    register_news_routes(app, "/news")
if register_notes_routes:
    register_notes_routes(app, "/notes")
if register_settings_routes:
    register_settings_routes(app, "/settings")
if register_weather_routes:
    register_weather_routes(app, "/weather")
if register_youtubewap_routes:
    register_youtubewap_routes(app, "/youtubewap")


@app.route("/icons/<path:filename>")
def app_icon(filename):
    filename = secure_filename(filename)
    icon_path = os.path.join(ICONS_DIR, filename)
    if os.path.isfile(icon_path):
        return send_from_directory(ICONS_DIR, filename)
    resp = make_response(BLANK_ICON)
    resp.headers["Content-Type"] = "image/png"
    return resp


@app.route("/")
def root():
    apps = [
        {"name": "Minigram", "label": "TG Mini", "url": "/contacts", "icon": "minigram.png"},
        {"name": "Weather", "url": "/weather", "icon": "weather.png", "disabled": WEATHER_IMPORT_ERROR is not None},
        {"name": "Notes", "url": "/notes", "icon": "notes.png", "disabled": NOTES_IMPORT_ERROR is not None},
        {"name": "AI", "url": "/ai", "icon": "ai.png", "disabled": AI_IMPORT_ERROR is not None},
        {"name": "Finance", "url": "/finance", "icon": "finance.png", "disabled": FINANCE_IMPORT_ERROR is not None},
        {"name": "Boards", "url": "/boards", "icon": "boards.png", "disabled": BOARDS_IMPORT_ERROR is not None},
        {"name": "Gmail", "url": "/mail", "icon": "gmail.png", "disabled": MAIL_IMPORT_ERROR is not None},
        {"name": "News", "url": "/news", "icon": "news.png", "disabled": NEWS_IMPORT_ERROR is not None},
        {"name": "YouTube", "label": "YT WAP", "url": "/youtubewap", "icon": "youtube.png", "disabled": YOUTUBEWAP_IMPORT_ERROR is not None},
        {"name": "Settings", "label": "Settings", "url": "/settings", "icon": "settings.png", "disabled": SETTINGS_IMPORT_ERROR is not None},
    ]
    body, css = app_drawer(apps, slots=12)
    if WEATHER_IMPORT_ERROR:
        body += f"<div class='muted'>Weather unavailable: {html_escape(str(WEATHER_IMPORT_ERROR))}</div>"
    if NOTES_IMPORT_ERROR:
        body += f"<div class='muted'>Notes unavailable: {html_escape(str(NOTES_IMPORT_ERROR))}</div>"
    if AI_IMPORT_ERROR:
        body += f"<div class='muted'>AI unavailable: {html_escape(str(AI_IMPORT_ERROR))}</div>"
    if FINANCE_IMPORT_ERROR:
        body += f"<div class='muted'>Finance unavailable: {html_escape(str(FINANCE_IMPORT_ERROR))}</div>"
    if BOARDS_IMPORT_ERROR:
        body += f"<div class='muted'>Boards unavailable: {html_escape(str(BOARDS_IMPORT_ERROR))}</div>"
    if MAIL_IMPORT_ERROR:
        body += f"<div class='muted'>Gmail unavailable: {html_escape(str(MAIL_IMPORT_ERROR))}</div>"
    if NEWS_IMPORT_ERROR:
        body += f"<div class='muted'>News unavailable: {html_escape(str(NEWS_IMPORT_ERROR))}</div>"
    if SETTINGS_IMPORT_ERROR:
        body += f"<div class='muted'>Settings unavailable: {html_escape(str(SETTINGS_IMPORT_ERROR))}</div>"
    if YOUTUBEWAP_IMPORT_ERROR:
        body += f"<div class='muted'>YouTube WAP unavailable: {html_escape(str(YOUTUBEWAP_IMPORT_ERROR))}</div>"
    return phone_page("MiniOS by fl0w", body, extra_css=css)


if __name__ == "__main__":
    print("MiniOS starting...")
    print(f"Listening on 0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
