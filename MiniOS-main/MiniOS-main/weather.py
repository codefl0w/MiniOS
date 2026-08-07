import json
import logging
import os
import time
from datetime import datetime

import requests
from env_loader import load_env
from flask import Flask, jsonify
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_env()

from settings import app_settings
from ui import h, phone_page

# ---- Configuration ----
DEFAULT_LOCATION_NAME = "Dursunlu"
DEFAULT_LATITUDE = 36.16736
DEFAULT_LONGITUDE = 36.15788
DEFAULT_TIMEZONE = "Europe/Istanbul"
DEFAULT_TEMPERATURE_UNIT = "celsius"
CACHE_TTL = int(os.environ.get("WEATHER_CACHE_TTL", "900"))
DATA_FILE = os.path.join(os.path.dirname(__file__), "dursunlu_weather.json")
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

CURRENT_FIELDS = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "precipitation",
    "weather_code",
    "cloud_cover",
    "pressure_msl",
    "wind_speed_10m",
    "wind_direction_10m",
]
HOURLY_FIELDS = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "precipitation_probability",
    "precipitation",
    "weather_code",
    "cloud_cover",
    "wind_speed_10m",
]

WEATHER_CODES = {
    0: "Clear",
    1: "Mostly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    56: "Freezing drizzle",
    57: "Freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light showers",
    81: "Showers",
    82: "Heavy showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunder hail",
    99: "Thunder hail",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def create_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "ProjectTCL/1.0"})
    return session


SESSION = create_session()
app = Flask(__name__)
_cache = {"data": None, "ts": 0, "cfg": None}


def weather_config():
    cfg = app_settings("weather")
    temp_unit = str(cfg.get("temperature_unit", DEFAULT_TEMPERATURE_UNIT)).lower()
    if temp_unit not in ("celsius", "fahrenheit"):
        temp_unit = DEFAULT_TEMPERATURE_UNIT
    return {
        "location_name": cfg.get("location_name", DEFAULT_LOCATION_NAME),
        "latitude": float(cfg.get("latitude", DEFAULT_LATITUDE)),
        "longitude": float(cfg.get("longitude", DEFAULT_LONGITUDE)),
        "timezone": cfg.get("timezone", DEFAULT_TIMEZONE),
        "temperature_unit": temp_unit,
    }


def unit(units, key, default=""):
    return units.get(key, default) if units else default


def value_with_unit(value, units, key):
    if value is None:
        return None
    suffix = unit(units, key)
    return f"{value}{suffix}" if suffix else str(value)


def weather_text(code):
    try:
        return WEATHER_CODES.get(int(code), f"Code {code}")
    except Exception:
        return "Unknown"


def short_time(value):
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%H:%M")
    except Exception:
        return value[-5:]


def fetch_weather_data():
    cfg = weather_config()
    params = {
        "latitude": cfg["latitude"],
        "longitude": cfg["longitude"],
        "timezone": cfg["timezone"],
        "current": ",".join(CURRENT_FIELDS),
        "hourly": ",".join(HOURLY_FIELDS),
        "forecast_hours": 24,
        "wind_speed_unit": "kmh",
    }
    if cfg["temperature_unit"] == "fahrenheit":
        params["temperature_unit"] = "fahrenheit"
    try:
        resp = SESSION.get(OPEN_METEO_URL, params=params, timeout=12)
        resp.raise_for_status()
        raw = resp.json()
        return normalize_weather(raw, cfg)
    except requests.Timeout:
        logging.error("Open-Meteo request timed out")
    except requests.HTTPError as exc:
        logging.error("Open-Meteo HTTP error: %s", exc.response.status_code)
    except requests.RequestException as exc:
        logging.error("Open-Meteo network error: %s", exc)
    except Exception as exc:
        logging.error("Open-Meteo parse error: %s", exc, exc_info=True)
    return None


def normalize_weather(raw, cfg):
    current = raw.get("current", {})
    current_units = raw.get("current_units", {})
    hourly = raw.get("hourly", {})
    hourly_units = raw.get("hourly_units", {})

    code = current.get("weather_code")
    data = {
        "current": {
            "location": cfg["location_name"],
            "time": short_time(current.get("time")),
            "temp": value_with_unit(current.get("temperature_2m"), current_units, "temperature_2m"),
            "felt_temp": value_with_unit(current.get("apparent_temperature"), current_units, "apparent_temperature"),
            "humidity": value_with_unit(current.get("relative_humidity_2m"), current_units, "relative_humidity_2m"),
            "wind": value_with_unit(current.get("wind_speed_10m"), current_units, "wind_speed_10m"),
            "wind_dir": value_with_unit(current.get("wind_direction_10m"), current_units, "wind_direction_10m"),
            "pressure": value_with_unit(current.get("pressure_msl"), current_units, "pressure_msl"),
            "precip": value_with_unit(current.get("precipitation"), current_units, "precipitation"),
            "cloudiness": value_with_unit(current.get("cloud_cover"), current_units, "cloud_cover"),
            "condition": weather_text(code),
            "weather_code": code,
        },
        "hourly": [],
        "meta": {
            "source": "Open-Meteo",
            "attribution": "Weather data by Open-Meteo.com",
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "coordinates": f"{cfg['latitude']:.5f},{cfg['longitude']:.5f}",
            "timezone": cfg["timezone"],
        },
    }

    times = hourly.get("time", [])
    for i, stamp in enumerate(times[:12]):
        code = hourly_value(hourly, "weather_code", i)
        data["hourly"].append(
            {
                "time": short_time(stamp),
                "temp": value_with_unit(hourly_value(hourly, "temperature_2m", i), hourly_units, "temperature_2m"),
                "felt_temp": value_with_unit(hourly_value(hourly, "apparent_temperature", i), hourly_units, "apparent_temperature"),
                "humidity": value_with_unit(hourly_value(hourly, "relative_humidity_2m", i), hourly_units, "relative_humidity_2m"),
                "precip_prob": value_with_unit(hourly_value(hourly, "precipitation_probability", i), hourly_units, "precipitation_probability"),
                "precip": value_with_unit(hourly_value(hourly, "precipitation", i), hourly_units, "precipitation"),
                "wind": value_with_unit(hourly_value(hourly, "wind_speed_10m", i), hourly_units, "wind_speed_10m"),
                "cloudiness": value_with_unit(hourly_value(hourly, "cloud_cover", i), hourly_units, "cloud_cover"),
                "condition": weather_text(code),
                "weather_code": code,
            }
        )
    return data


def hourly_value(hourly, key, index):
    values = hourly.get(key) or []
    if index >= len(values):
        return None
    return values[index]


def save_to_disk(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logging.error("Failed to write weather data file: %s", exc)


def load_from_disk():
    if not os.path.exists(DATA_FILE):
        return None
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logging.error("Failed to load weather data file: %s", exc)
        return None


def get_weather(force_refresh=False):
    now = time.time()
    cfg = weather_config()
    if not force_refresh and _cache["data"] and _cache["cfg"] == cfg and now - _cache["ts"] < CACHE_TTL:
        return _cache["data"]

    fetched = fetch_weather_data()
    if fetched:
        _cache["data"] = fetched
        _cache["ts"] = now
        _cache["cfg"] = cfg
        save_to_disk(fetched)
        return fetched

    loaded = load_from_disk()
    if loaded:
        _cache["data"] = loaded
        _cache["ts"] = now
        _cache["cfg"] = cfg
        loaded.setdefault("meta", {})["stale"] = True
        return loaded

    return {"current": {"location": weather_config()["location_name"]}, "hourly": [], "meta": {"source": "Open-Meteo", "stale": True}}


def join_path(base_path, path):
    base = base_path.rstrip("/")
    return f"{base}{path}" if base else path


def render_weather_html(data, base_path="", home_url=None):
    current = data.get("current", {})
    hourly = data.get("hourly", [])
    meta = data.get("meta", {})
    refresh_url = join_path(base_path, "/refresh")
    raw_url = join_path(base_path, "/raw")
    nav = []
    if home_url:
        nav.append(("Apps", home_url))
    nav.extend([("Refresh", refresh_url), ("Raw", raw_url)])

    body = f"""
<div class="temp">{h(current.get("temp"), "-")}</div>
<div class="desc">{h(current.get("condition"), "-")}</div>
"""
    rows = [
        ("Feels", current.get("felt_temp")),
        ("Humidity", current.get("humidity")),
        ("Wind", current.get("wind")),
        ("Dir", current.get("wind_dir")),
        ("Pressure", current.get("pressure")),
        ("Rain", current.get("precip")),
        ("Clouds", current.get("cloudiness")),
        ("Time", current.get("time")),
    ]
    for label, value in rows:
        if value:
            body += f"<div class='row'><span class='k'>{h(label)}</span><span class='v'>{h(value)}</span></div>"

    stale = " stale" if meta.get("stale") else ""
    body += f"<div class='small'>Updated: {h(meta.get('last_updated'), '-')}{stale}</div>"
    body += "<h3>Hourly</h3>"
    if not hourly:
        body += "<div class='small'>No hourly data</div>"
    for item in hourly[:8]:
        body += "<div class='hour'>"
        body += f"<strong>{h(item.get('time'), '-')}</strong> {h(item.get('temp'), '-')}"
        body += f"<br><span class='small'>{h(item.get('condition'), '-')}"
        if item.get("precip_prob"):
            body += f" | rain {h(item.get('precip_prob'))}"
        if item.get("wind"):
            body += f" | wind {h(item.get('wind'))}"
        body += "</span></div>"

    body += "<div class='small'>Source: <a href='https://open-meteo.com/'>Open-Meteo</a></div>"

    css = """
.temp{font-size:28px;font-weight:bold;color:#ffd35a;margin:2px 0;}
.desc{color:#cfe9ff;margin-bottom:6px;}
.row{border-top:1px solid #263241;padding:4px 0;overflow:hidden;}
.k{color:#95a3b3;}
.v{float:right;color:#fff;max-width:130px;text-align:right;}
.hour{border-top:1px solid #263241;padding:5px 0;}
.small{color:#8996a5;font-size:11px;}
"""
    return phone_page(current.get("location") or "Weather", body, nav=nav, extra_css=css)


def register_weather_routes(flask_app, prefix="/weather"):
    base = prefix.rstrip("/")

    @flask_app.route(base)
    @flask_app.route(base + "/")
    def weather_index():
        return render_weather_html(get_weather(), base_path=base, home_url="/")

    @flask_app.route(base + "/raw")
    def weather_raw_json():
        return jsonify(get_weather())

    @flask_app.route(base + "/refresh")
    def weather_refresh():
        return render_weather_html(get_weather(force_refresh=True), base_path=base, home_url="/")

    @flask_app.route(base + "/health")
    def weather_health():
        cache_age = time.time() - _cache["ts"] if _cache["ts"] > 0 else -1
        return jsonify(
            {
                "status": "ok",
                "cache_age_seconds": cache_age,
                "has_cached_data": _cache["data"] is not None,
                "source": "Open-Meteo",
            }
        )


@app.route("/")
def index():
    return render_weather_html(get_weather())


@app.route("/raw")
def raw_json():
    return jsonify(get_weather())


@app.route("/refresh")
def refresh():
    return render_weather_html(get_weather(force_refresh=True))


@app.route("/health")
def health():
    cache_age = time.time() - _cache["ts"] if _cache["ts"] > 0 else -1
    return jsonify(
        {
            "status": "ok",
            "cache_age_seconds": cache_age,
            "has_cached_data": _cache["data"] is not None,
            "source": "Open-Meteo",
        }
    )


if __name__ == "__main__":
    logging.info("Starting Open-Meteo weather service...")
    get_weather(force_refresh=True)
    app.run(host="0.0.0.0", port=8000, debug=False)
