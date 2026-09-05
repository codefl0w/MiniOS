import base64
import os
from html import escape as html_escape

from env_loader import load_env
from flask import Flask, make_response, redirect, request, send_from_directory
from werkzeug.utils import secure_filename

load_env()

from minigram import PORT, register_minigram_routes
from ui import app_drawer, phone_page, welcome_popup

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
    from duckduckgo import register_duckduckgo_routes
    DUCKDUCKGO_IMPORT_ERROR = None
except Exception as exc:
    register_duckduckgo_routes = None
    DUCKDUCKGO_IMPORT_ERROR = exc

try:
    from settings import register_settings_routes, app_settings, update_app_settings
    SETTINGS_IMPORT_ERROR = None
except Exception as exc:
    register_settings_routes = None
    app_settings = None
    update_app_settings = None
    SETTINGS_IMPORT_ERROR = exc

try:
    from weather import register_weather_routes
    WEATHER_IMPORT_ERROR = None
except Exception as exc:
    register_weather_routes = None
    WEATHER_IMPORT_ERROR = exc

try:
    from calendar_app import register_calendar_routes
    CALENDAR_IMPORT_ERROR = None
except Exception as exc:
    register_calendar_routes = None
    CALENDAR_IMPORT_ERROR = exc

BASE_DIR = os.path.dirname(__file__)
ICONS_DIR = os.path.abspath(os.environ.get("ICONS_DIR", os.path.join(BASE_DIR, "icons")))
GITHUB_RES_DIR = os.path.abspath(os.path.join(BASE_DIR, "github_res"))
os.makedirs(ICONS_DIR, exist_ok=True)
os.makedirs(GITHUB_RES_DIR, exist_ok=True)
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
if register_duckduckgo_routes:
    register_duckduckgo_routes(app, "/duckduckgo")
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
if register_calendar_routes:
    register_calendar_routes(app, "/calendar")


@app.route("/icons/<path:filename>")
def app_icon(filename):
    filename = secure_filename(filename)
    icon_path = os.path.join(ICONS_DIR, filename)
    if os.path.isfile(icon_path):
        return send_from_directory(ICONS_DIR, filename)
    resp = make_response(BLANK_ICON)
    resp.headers["Content-Type"] = "image/png"
    return resp


@app.route("/github_res/<path:filename>")
def github_resource(filename):
    filename = secure_filename(filename)
    file_path = os.path.join(GITHUB_RES_DIR, filename)
    if os.path.isfile(file_path):
        return send_from_directory(GITHUB_RES_DIR, filename)
    return make_response("Not found", 404)


@app.route("/welcome/dismiss", methods=["GET", "POST"])
def welcome_dismiss():
    if update_app_settings:
        try:
            update_app_settings("ui", {"welcome_seen": True})
        except Exception:
            pass
    resp = redirect("/")
    resp.set_cookie("minios_welcome", "1", max_age=31536000, path="/")
    return resp


@app.route("/")
def root():
    disabled_apps = []
    if app_settings:
        try:
            disabled_apps = app_settings("apps").get("disabled", [])
        except Exception:
            pass

    apps = [
        {"name": "Minigram", "label": "TG Mini", "url": "/contacts", "icon": "minigram.png"},
        {"name": "DuckDuckGo", "label": "DuckDuckGo", "url": "/duckduckgo", "icon": "duckduckgo.png", "disabled": DUCKDUCKGO_IMPORT_ERROR is not None},
        {"name": "Weather", "url": "/weather", "icon": "weather.png", "disabled": WEATHER_IMPORT_ERROR is not None},
        {"name": "Notes", "url": "/notes", "icon": "notes.png", "disabled": NOTES_IMPORT_ERROR is not None},
        {"name": "AI", "url": "/ai", "icon": "ai.png", "disabled": AI_IMPORT_ERROR is not None},
        {"name": "Finance", "url": "/finance", "icon": "finance.png", "disabled": FINANCE_IMPORT_ERROR is not None},
        {"name": "Boards", "url": "/boards", "icon": "boards.png", "disabled": BOARDS_IMPORT_ERROR is not None},
        {"name": "Gmail", "url": "/mail", "icon": "gmail.png", "disabled": MAIL_IMPORT_ERROR is not None},
        {"name": "News", "url": "/news", "icon": "news.png", "disabled": NEWS_IMPORT_ERROR is not None},
        {"name": "Calendar", "url": "/calendar", "icon": "calendar.png", "disabled": CALENDAR_IMPORT_ERROR is not None},
        {"name": "Settings", "label": "Settings", "url": "/settings", "icon": "settings.png", "disabled": SETTINGS_IMPORT_ERROR is not None},
    ]
    apps = [a for a in apps if a["name"] not in disabled_apps]
    body, css = app_drawer(apps)
    if CALENDAR_IMPORT_ERROR and "Calendar" not in disabled_apps:
        body += f"<div class='muted'>Calendar unavailable: {html_escape(str(CALENDAR_IMPORT_ERROR))}</div>"
    if DUCKDUCKGO_IMPORT_ERROR and "DuckDuckGo" not in disabled_apps:
        body += f"<div class='muted'>DuckDuckGo unavailable: {html_escape(str(DUCKDUCKGO_IMPORT_ERROR))}</div>"
    if WEATHER_IMPORT_ERROR and "Weather" not in disabled_apps:
        body += f"<div class='muted'>Weather unavailable: {html_escape(str(WEATHER_IMPORT_ERROR))}</div>"
    if NOTES_IMPORT_ERROR and "Notes" not in disabled_apps:
        body += f"<div class='muted'>Notes unavailable: {html_escape(str(NOTES_IMPORT_ERROR))}</div>"
    if AI_IMPORT_ERROR and "AI" not in disabled_apps:
        body += f"<div class='muted'>AI unavailable: {html_escape(str(AI_IMPORT_ERROR))}</div>"
    if FINANCE_IMPORT_ERROR and "Finance" not in disabled_apps:
        body += f"<div class='muted'>Finance unavailable: {html_escape(str(FINANCE_IMPORT_ERROR))}</div>"
    if BOARDS_IMPORT_ERROR and "Boards" not in disabled_apps:
        body += f"<div class='muted'>Boards unavailable: {html_escape(str(BOARDS_IMPORT_ERROR))}</div>"
    if MAIL_IMPORT_ERROR and "Gmail" not in disabled_apps:
        body += f"<div class='muted'>Gmail unavailable: {html_escape(str(MAIL_IMPORT_ERROR))}</div>"
    if NEWS_IMPORT_ERROR and "News" not in disabled_apps:
        body += f"<div class='muted'>News unavailable: {html_escape(str(NEWS_IMPORT_ERROR))}</div>"
    if SETTINGS_IMPORT_ERROR:
        body += f"<div class='muted'>Settings unavailable: {html_escape(str(SETTINGS_IMPORT_ERROR))}</div>"

    welcome_seen = False
    if app_settings:
        try:
            welcome_seen = bool(app_settings("ui").get("welcome_seen", False))
        except Exception:
            pass
    if not welcome_seen and request.cookies.get("minios_welcome") == "1":
        welcome_seen = True

    if not welcome_seen:
        pop_html, pop_css = welcome_popup()
        body += pop_html
        css += pop_css

    return phone_page("", body, extra_css=css)


if __name__ == "__main__":
    print("MiniOS starting...")
    print(f"Listening on 0.0.0.0:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
