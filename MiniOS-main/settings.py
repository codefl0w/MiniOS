import json
import os
from copy import deepcopy

from env_loader import load_env
from flask import redirect, request

load_env()

from ui import h, phone_page

BASE_DIR = os.path.dirname(__file__)
SETTINGS_PATH = os.environ.get("MINIOS_SETTINGS_PATH", os.path.join(BASE_DIR, "settings.json"))

DEFAULTS = {
    "minigram": {
        "contacts": [],
        "timezone": "Europe/Istanbul",
        "timestamp_format": "compact",
    },
    "weather": {
        "location_name": "Dursunlu",
        "latitude": 36.16736,
        "longitude": 36.15788,
        "timezone": "Europe/Istanbul",
        "temperature_unit": "celsius",
    },
    "finance": {
        "currency": "TL",
    },
    "boards": {
        "subreddits": [
            "4chan",
            "fightporn",
            "greentext",
            "itrunsdoom",
            "PSVitaHomebrew",
            "vita",
            "vitahacks",
            "vitapiracy",
        ],
        "default_sort": "hot",
    },
    "news": {
        "default_mode": "topic",
        "default_topic": "TECHNOLOGY",
        "default_lang": "en-US",
        "default_geo": "Turkey",
        "default_query": "technology",
    },
    "mail": {
        "limit": 40,
        "cache_ttl": 600,
    },
    "youtubewap": {
        "default_query": "music",
        "limit": 12,
        "cache_ttl": 900,
    },
}

_cache = None


def merge_defaults(data, defaults):
    result = deepcopy(defaults)
    if not isinstance(data, dict):
        return result
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key].update(value)
        else:
            result[key] = value
    return result


def load_settings(force=False):
    global _cache
    if _cache is not None and not force:
        return _cache
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            loaded = json.load(f)
    except FileNotFoundError:
        loaded = {}
    except Exception:
        loaded = {}
    _cache = merge_defaults(loaded, DEFAULTS)
    return _cache


def save_settings(data):
    global _cache
    data = merge_defaults(data, DEFAULTS)
    tmp_path = SETTINGS_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, SETTINGS_PATH)
    _cache = data


def app_settings(name):
    return load_settings().get(name, deepcopy(DEFAULTS.get(name, {})))


def update_app_settings(name, values):
    data = load_settings()
    current = dict(data.get(name, {}))
    current.update(values)
    data[name] = current
    save_settings(data)


def lines_to_list(text):
    rows = []
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            rows.append(line)
    return rows


def list_to_lines(values):
    return "\n".join(values or [])


def as_int(value, default):
    try:
        return int(value)
    except Exception:
        return default


def as_float(value, default):
    try:
        return float(value)
    except Exception:
        return default


def normalize_minigram_contacts(raw_contacts):
    contacts = []
    seen_ids = set()
    if not isinstance(raw_contacts, list):
        return contacts
    for row in raw_contacts:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "")).strip()
        telegram_id = as_int(row.get("telegram_id"), 0)
        if not name or telegram_id <= 0 or telegram_id in seen_ids:
            continue
        contacts.append({"name": name, "telegram_id": telegram_id})
        seen_ids.add(telegram_id)
    return contacts


SETTINGS_CSS = """
.row{display:block;border-top:1px solid #263241;padding:8px 0;color:#fff;}
.small{display:block;color:#91a0af;font-size:11px;margin-top:2px;}
form{margin:0;}
input[type=text],textarea{width:100%;box-sizing:border-box;background:#fff;color:#000;border:0;padding:6px;font-size:13px;margin:0 0 5px;font-family:Arial;}
textarea{height:120px;}
input[type=submit]{background:#95e1ff;color:#000;border:0;padding:6px 8px;font-size:13px;}
.body{background:#0f1620;border:1px solid #263241;padding:6px;margin:6px 0;}
.field{margin:0 0 7px;}
.fieldname{color:#ffd35a;margin:0 0 2px;}
.hint{color:#91a0af;font-size:11px;margin:-3px 0 4px;}
"""


def save_button():
    return "<input type='submit' value='Save'>"


def field(label, control, hint=""):
    hint_html = f"<div class='hint'>{h(hint)}</div>" if hint else ""
    return f"<div class='field'><div class='fieldname'>{h(label)}</div>{hint_html}{control}</div>"


def register_settings_routes(flask_app, prefix="/settings"):
    base = prefix.rstrip("/")

    @flask_app.route(base)
    @flask_app.route(base + "/")
    def settings_index():
        rows = [
            ("Minigram", "Contacts and timestamps", f"{base}/minigram"),
            ("Weather", "Location and coordinates", f"{base}/weather"),
            ("Finance", "Currency", f"{base}/finance"),
            ("Boards", "Subreddits and sort", f"{base}/boards"),
            ("News", "Google News defaults", f"{base}/news"),
            ("Gmail", "Limit and cache TTL", f"{base}/mail"),
            ("YouTube WAP", "Search defaults and cache", f"{base}/youtubewap"),
            ("About", "MiniOS info", f"{base}/about"),
        ]
        body = ""
        for name, desc, url in rows:
            body += f"<a class='row' href='{h(url)}'><strong>{h(name)}</strong><span class='small'>{h(desc)}</span></a>"
        return phone_page("Settings", body, nav=[("Apps", "/")], extra_css=SETTINGS_CSS)

    @flask_app.route(base + "/minigram", methods=["GET", "POST"])
    def settings_minigram():
        current = app_settings("minigram")
        contacts = normalize_minigram_contacts(current.get("contacts", []))
        error = ""

        if request.method == "POST":
            action = request.form.get("action", "prefs")
            if action == "prefs":
                fmt = request.form.get("timestamp_format", "").strip() or current.get("timestamp_format", "compact")
                if fmt not in ("compact", "full"):
                    fmt = "compact"
                update_app_settings(
                    "minigram",
                    {
                        "contacts": contacts,
                        "timezone": request.form.get("timezone", "").strip() or current.get("timezone", "Europe/Istanbul"),
                        "timestamp_format": fmt,
                    },
                )
                return redirect(base + "/minigram")

            if action == "delete":
                delete_id = as_int(request.form.get("telegram_id"), 0)
                contacts = [contact for contact in contacts if contact["telegram_id"] != delete_id]
                update_app_settings("minigram", {"contacts": contacts})
                return redirect(base + "/minigram")

            if action == "add":
                name = request.form.get("name", "").strip()
                telegram_id = as_int(request.form.get("telegram_id"), 0)
                if not name:
                    error = "Name required."
                elif telegram_id <= 0:
                    error = "Telegram ID must be numeric."
                elif any(contact["name"].lower() == name.lower() and contact["telegram_id"] != telegram_id for contact in contacts):
                    error = "Name already used by another ID."
                else:
                    updated = False
                    for contact in contacts:
                        if contact["telegram_id"] == telegram_id:
                            contact["name"] = name
                            updated = True
                            break
                    if not updated:
                        contacts.append({"name": name, "telegram_id": telegram_id})
                    update_app_settings("minigram", {"contacts": contacts})
                    return redirect(base + "/minigram")

        tz = current.get("timezone", "Europe/Istanbul")
        fmt = current.get("timestamp_format", "compact")
        error_html = f"<div class='body'>{h(error)}</div>" if error else ""
        contact_html = "<div class='body'><strong>Contacts</strong><br>"
        if contacts:
            for contact in contacts:
                contact_html += f"""
<form method="post" action="{base}/minigram">
<input type="hidden" name="action" value="delete">
<input type="hidden" name="telegram_id" value="{contact["telegram_id"]}">
<div class="row">
<strong>{h(contact["name"])}</strong><span class="small">{contact["telegram_id"]}</span>
<input type="submit" value="Delete">
</div>
</form>
"""
        else:
            contact_html += "<span class='small'>No contacts yet.</span>"
        contact_html += "</div>"

        body = f"""
{error_html}
<form method="post" action="{base}/minigram">
<input type="hidden" name="action" value="prefs">
{field("Timezone", f'<input type="text" name="timezone" value="{h(tz)}">', "Example: Europe/Istanbul")}
{field("Timestamp format", f'<input type="text" name="timestamp_format" value="{h(fmt)}">', "compact or full")}
{save_button()}
</form>
<div class="body">
<strong>Add contact</strong>
<form method="post" action="{base}/minigram">
<input type="hidden" name="action" value="add">
{field("Name", '<input type="text" name="name" value="">')}
{field("Telegram ID", '<input type="text" name="telegram_id" value="">', "Numeric Telegram user ID")}
{save_button()}
</form>
</div>
{contact_html}
"""
        return phone_page("Minigram Settings", body, nav=[("Settings", base)], extra_css=SETTINGS_CSS)

    @flask_app.route(base + "/weather", methods=["GET", "POST"])
    def settings_weather():
        current = app_settings("weather")
        if request.method == "POST":
            update_app_settings(
                "weather",
                {
                    "location_name": request.form.get("location_name", "").strip() or current["location_name"],
                    "latitude": as_float(request.form.get("latitude"), current["latitude"]),
                    "longitude": as_float(request.form.get("longitude"), current["longitude"]),
                    "timezone": request.form.get("timezone", "").strip() or current["timezone"],
                    "temperature_unit": request.form.get("temperature_unit", "").strip() or current["temperature_unit"],
                },
            )
            return redirect(base)
        temp_unit = current.get("temperature_unit", "celsius")
        body = f"""
<form method="post" action="{base}/weather">
{field("Location name", f'<input type="text" name="location_name" value="{h(current["location_name"])}">')}
{field("Latitude", f'<input type="text" name="latitude" value="{h(current["latitude"])}">')}
{field("Longitude", f'<input type="text" name="longitude" value="{h(current["longitude"])}">')}
{field("Timezone", f'<input type="text" name="timezone" value="{h(current["timezone"])}">', "Example: Europe/Istanbul")}
{field("Temperature unit", f'<input type="text" name="temperature_unit" value="{h(temp_unit)}">', "celsius or fahrenheit")}
{save_button()}
</form>
"""
        return phone_page("Weather Settings", body, nav=[("Settings", base)], extra_css=SETTINGS_CSS)

    @flask_app.route(base + "/finance", methods=["GET", "POST"])
    def settings_finance():
        current = app_settings("finance")
        if request.method == "POST":
            update_app_settings("finance", {"currency": request.form.get("currency", "").strip() or current["currency"]})
            return redirect(base)
        body = f"""
<form method="post" action="{base}/finance">
{field("Currency", f'<input type="text" name="currency" value="{h(current["currency"])}">', "Displayed after totals, for example TL or USD")}
{save_button()}
</form>
"""
        return phone_page("Finance Settings", body, nav=[("Settings", base)], extra_css=SETTINGS_CSS)

    @flask_app.route(base + "/boards", methods=["GET", "POST"])
    def settings_boards():
        current = app_settings("boards")
        if request.method == "POST":
            sort = request.form.get("default_sort", "hot")
            if sort not in ("hot", "new", "top"):
                sort = "hot"
            update_app_settings(
                "boards",
                {
                    "subreddits": lines_to_list(request.form.get("subreddits", "")),
                    "default_sort": sort,
                },
            )
            return redirect(base)
        body = f"""
<form method="post" action="{base}/boards">
{field("Followed subreddits", f'<textarea name="subreddits">{h(list_to_lines(current["subreddits"]))}</textarea>', "One subreddit per line")}
{field("Default sort", f'<input type="text" name="default_sort" value="{h(current["default_sort"])}">', "hot, new, or top")}
{save_button()}
</form>
"""
        return phone_page("Boards Settings", body, nav=[("Settings", base)], extra_css=SETTINGS_CSS)

    @flask_app.route(base + "/news", methods=["GET", "POST"])
    def settings_news():
        current = app_settings("news")
        if request.method == "POST":
            update_app_settings(
                "news",
                {
                    "default_mode": request.form.get("default_mode", "").strip() or current["default_mode"],
                    "default_topic": request.form.get("default_topic", "").strip().upper() or current["default_topic"],
                    "default_lang": request.form.get("default_lang", "").strip() or current["default_lang"],
                    "default_geo": request.form.get("default_geo", "").strip() or current["default_geo"],
                    "default_query": request.form.get("default_query", "").strip() or current["default_query"],
                },
            )
            return redirect(base)
        body = f"""
<form method="post" action="{base}/news">
{field("Default mode", f'<input type="text" name="default_mode" value="{h(current["default_mode"])}">', "top, topic, geo, or search")}
{field("Default topic", f'<input type="text" name="default_topic" value="{h(current["default_topic"])}">', "WORLD, NATION, BUSINESS, TECHNOLOGY, ENTERTAINMENT, SCIENCE, SPORTS, HEALTH")}
{field("Default language", f'<input type="text" name="default_lang" value="{h(current["default_lang"])}">', "Example: en-US or tr-TR")}
{field("Default geo", f'<input type="text" name="default_geo" value="{h(current["default_geo"])}">', "Used by geo mode")}
{field("Default search query", f'<input type="text" name="default_query" value="{h(current["default_query"])}">', "Used by search mode")}
{save_button()}
</form>
"""
        return phone_page("News Settings", body, nav=[("Settings", base)], extra_css=SETTINGS_CSS)

    @flask_app.route(base + "/mail", methods=["GET", "POST"])
    def settings_mail():
        current = app_settings("mail")
        if request.method == "POST":
            update_app_settings(
                "mail",
                {
                    "limit": as_int(request.form.get("limit"), current["limit"]),
                    "cache_ttl": as_int(request.form.get("cache_ttl"), current["cache_ttl"]),
                },
            )
            return redirect(base)
        body = f"""
<form method="post" action="{base}/mail">
{field("Mail limit", f'<input type="text" name="limit" value="{h(current["limit"])}">', "Number of recent mails cached")}
{field("Cache TTL", f'<input type="text" name="cache_ttl" value="{h(current["cache_ttl"])}">', "Seconds before auto-refresh")}
{save_button()}
</form>
<div class="small">Gmail address and app password stay in .env only.</div>
"""
        return phone_page("Gmail Settings", body, nav=[("Settings", base)], extra_css=SETTINGS_CSS)

    @flask_app.route(base + "/youtubewap", methods=["GET", "POST"])
    def settings_youtubewap():
        current = app_settings("youtubewap")
        if request.method == "POST":
            update_app_settings(
                "youtubewap",
                {
                    "default_query": request.form.get("default_query", "").strip() or current["default_query"],
                    "limit": as_int(request.form.get("limit"), current["limit"]),
                    "cache_ttl": as_int(request.form.get("cache_ttl"), current["cache_ttl"]),
                },
            )
            return redirect(base)
        body = f"""
<form method="post" action="{base}/youtubewap">
{field("Default search query", f'<input type="text" name="default_query" value="{h(current["default_query"])}">')}
{field("Result limit", f'<input type="text" name="limit" value="{h(current["limit"])}">', "1 to 25 videos")}
{field("Cache TTL", f'<input type="text" name="cache_ttl" value="{h(current["cache_ttl"])}">', "Seconds before auto-refresh")}
{save_button()}
</form>
"""
        return phone_page("YouTube WAP Settings", body, nav=[("Settings", base)], extra_css=SETTINGS_CSS)

    @flask_app.route(base + "/about")
    def settings_about():
        body = """
<div class="row"><strong>MiniOS Version:</strong><span class="small">V1.0.0</span></div>
<div class="row"><strong>Made by:</strong><span class="small">fl0w</span></div>
<div class="row"><strong>Platform:</strong><span class="small">Flask</span></div>
<div class="row"><strong>Target:</strong><span class="small">Opera Mini / Dorado @ 240x320</span></div>
"""
        return phone_page("About", body, nav=[("Settings", base)], extra_css=SETTINGS_CSS)
