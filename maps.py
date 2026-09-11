import hashlib
import json
import math
import os
import re
import sqlite3
import time
from io import BytesIO

from flask import Response, redirect, request
from PIL import Image, ImageDraw
import requests
from ui import h, phone_page

BASE_DIR = os.path.dirname(__file__)
MAPS_DB_PATH = os.environ.get("MAPS_DB_PATH", os.path.join(BASE_DIR, "maps.db"))

USER_AGENT = "MiniOS/1.0 (self-hosted feature phone OS; +https://github.com/codefl0w/MiniOS)"
HEADERS = {"User-Agent": USER_AGENT}


def connect_db():
    conn = sqlite3.connect(MAPS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_maps_db():
    conn = connect_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS geocode_cache (
            query TEXT PRIMARY KEY,
            lat REAL NOT NULL,
            lon REAL NOT NULL,
            display_name TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tile_cache (
            key TEXT PRIMARY KEY,
            data BLOB NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS routes_cache (
            id TEXT PRIMARY KEY,
            from_query TEXT NOT NULL,
            to_query TEXT NOT NULL,
            from_name TEXT NOT NULL,
            to_name TEXT NOT NULL,
            mode TEXT NOT NULL,
            distance REAL NOT NULL,
            duration REAL NOT NULL,
            steps_json TEXT NOT NULL,
            coords_json TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recent_routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_name TEXT NOT NULL,
            to_name TEXT NOT NULL,
            from_query TEXT NOT NULL,
            to_query TEXT NOT NULL,
            mode TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


init_maps_db()


# ---------------------------------------------------------------------------
# Slippy tile math
# ---------------------------------------------------------------------------
def lat_lon_to_xy(lat, lon, zoom):
    n = 2.0 ** zoom
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    # Clamp lat to valid Mercator range (-85.0511 to 85.0511)
    lat_rad = max(min(lat_rad, 1.4844), -1.4844)
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def fetch_tile(z, x, y):
    key = f"{z}/{x}/{y}"
    conn = connect_db()
    row = conn.execute("SELECT data FROM tile_cache WHERE key = ?", (key,)).fetchone()
    if row:
        conn.close()
        return row["data"]

    url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    data = None
    try:
        r = requests.get(url, headers=HEADERS, timeout=5)
        if r.status_code == 200:
            data = r.content
            conn.execute(
                "INSERT OR REPLACE INTO tile_cache (key, data, created_at) VALUES (?, ?, ?)",
                (key, data, time.time()),
            )
            conn.commit()
    except Exception:
        data = None
    finally:
        conn.close()

    return data


# ---------------------------------------------------------------------------
# Geocoding (Coordinates or Nominatim)
# ---------------------------------------------------------------------------
COORD_RE = re.compile(r"^\s*([+-]?[0-9]+(?:\.[0-9]+)?)\s*,\s*([+-]?[0-9]+(?:\.[0-9]+)?)\s*$")


def shorten_place_name(full_name):
    parts = [p.strip() for p in full_name.split(",") if p.strip()]
    if len(parts) <= 2:
        return full_name
    return ", ".join(parts[:2])


def geocode_location(query):
    if not query:
        return None

    query = query.strip()
    match = COORD_RE.match(query)
    if match:
        try:
            lat = float(match.group(1))
            lon = float(match.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon, f"{lat:.4f}, {lon:.4f}"
        except ValueError:
            pass

    key = query.lower()
    conn = connect_db()
    row = conn.execute("SELECT lat, lon, display_name FROM geocode_cache WHERE query = ?", (key,)).fetchone()
    if row:
        conn.close()
        return row["lat"], row["lon"], row["display_name"]
    conn.close()

    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": query, "format": "json", "limit": 1}
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=6)
        if r.status_code == 200:
            data = r.json()
            if data:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                short_name = shorten_place_name(data[0].get("display_name", query))
                conn = connect_db()
                conn.execute(
                    "INSERT OR REPLACE INTO geocode_cache (query, lat, lon, display_name, created_at) VALUES (?, ?, ?, ?, ?)",
                    (key, lat, lon, short_name, time.time()),
                )
                conn.commit()
                conn.close()
                return lat, lon, short_name
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Routing (OSRM)
# ---------------------------------------------------------------------------
def format_step_instruction(step, mode="foot"):
    man = step.get("maneuver", {})
    mtype = man.get("type", "")
    mmod = man.get("modifier", "").strip()
    name = step.get("name", "").strip()
    dist = step.get("distance", 0)

    verb = "walk" if mode == "foot" else ("drive" if mode == "driving" else "ride")
    if dist < 1000:
        dist_str = f"{int(round(dist))}m"
    else:
        dist_str = f"{dist / 1000.0:.1f}km"

    if mtype == "depart":
        dir_text = f" {mmod}" if mmod else ""
        text = f"Depart{dir_text}" + (f" on {name}" if name else "")
    elif mtype == "arrive":
        return "Arrive at destination"
    elif mtype == "turn":
        text = f"Turn {mmod}" if mmod else "Turn"
        if name:
            text += f" onto {name}"
    elif mtype in ("continue", "new name"):
        text = "Continue" + (f" on {name}" if name else "")
    elif mtype == "fork":
        text = f"Keep {mmod}" if mmod else "Keep straight"
        if name:
            text += f" onto {name}"
    elif mtype == "roundabout":
        text = "Enter roundabout" + (f" and exit onto {name}" if name else "")
    elif mtype == "end of road":
        text = f"At end of road turn {mmod}" if mmod else "At end of road"
        if name:
            text += f" onto {name}"
    else:
        clean_type = mtype.replace("_", " ").capitalize()
        text = f"{clean_type} {mmod}".strip() + (f" onto {name}" if name else "")

    if dist > 0:
        return f"{text} ({verb} {dist_str})"
    return text


def fetch_osrm_route(lon1, lat1, lon2, lat2, mode="foot"):
    profile = "foot"
    if mode in ("driving", "car"):
        profile = "driving"
    elif mode in ("cycling", "bike"):
        profile = "bike"

    url = f"http://router.project-osrm.org/route/v1/{profile}/{lon1},{lat1};{lon2},{lat2}?overview=full&steps=true&geometries=geojson"
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            data = r.json()
            if data.get("code") == "Ok" and data.get("routes"):
                route = data["routes"][0]
                distance = route.get("distance", 0)
                duration = route.get("duration", 0)
                coords = route.get("geometry", {}).get("coordinates", [])

                steps = []
                for leg in route.get("legs", []):
                    for s in leg.get("steps", []):
                        instruction = format_step_instruction(s, profile)
                        steps.append(
                            {
                                "instruction": instruction,
                                "distance": s.get("distance", 0),
                            }
                        )

                return {
                    "distance": distance,
                    "duration": duration,
                    "steps": steps,
                    "coords": coords,
                }
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Static Map Rendering (Pillow)
# ---------------------------------------------------------------------------
def render_route_map(coords, target_w=240, target_h=180):
    if not coords or len(coords) < 2:
        img = Image.new("RGB", (target_w, target_h), (30, 40, 55))
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    # 25% margin padding
    pad_lat = max(max_lat - min_lat, 0.0008) * 0.25
    pad_lon = max(max_lon - min_lon, 0.0008) * 0.25
    b_min_lat, b_max_lat = min_lat - pad_lat, max_lat + pad_lat
    b_min_lon, b_max_lon = min_lon - pad_lon, max_lon + pad_lon

    chosen_zoom = 15
    for z in range(17, 3, -1):
        x0, y0 = lat_lon_to_xy(b_max_lat, b_min_lon, z)
        x1, y1 = lat_lon_to_xy(b_min_lat, b_max_lon, z)
        w_px = abs(x1 - x0) * 256
        h_px = abs(y1 - y0) * 256
        if w_px <= target_w and h_px <= target_h:
            chosen_zoom = z
            break

    center_lat = (min_lat + max_lat) / 2.0
    center_lon = (min_lon + max_lon) / 2.0
    c_x, c_y = lat_lon_to_xy(center_lat, center_lon, chosen_zoom)
    c_px = c_x * 256
    c_py = c_y * 256

    crop_x0 = int(c_px - target_w / 2)
    crop_y0 = int(c_py - target_h / 2)
    crop_x1 = crop_x0 + target_w
    crop_y1 = crop_y0 + target_h

    min_tx = crop_x0 // 256
    max_tx = crop_x1 // 256
    min_ty = crop_y0 // 256
    max_ty = crop_y1 // 256

    canvas_w = (max_tx - min_tx + 1) * 256
    canvas_h = (max_ty - min_ty + 1) * 256
    canvas = Image.new("RGB", (canvas_w, canvas_h), (215, 220, 225))

    for tx in range(min_tx, max_tx + 1):
        for ty in range(min_ty, max_ty + 1):
            tile_bytes = fetch_tile(chosen_zoom, tx, ty)
            if tile_bytes:
                try:
                    t_img = Image.open(BytesIO(tile_bytes)).convert("RGB")
                    canvas.paste(t_img, ((tx - min_tx) * 256, (ty - min_ty) * 256))
                except Exception:
                    pass

    draw = ImageDraw.Draw(canvas)

    pixel_pts = []
    for lon, lat in coords:
        pt_x, pt_y = lat_lon_to_xy(lat, lon, chosen_zoom)
        px = int(pt_x * 256 - min_tx * 256)
        py = int(pt_y * 256 - min_ty * 256)
        pixel_pts.append((px, py))

    if len(pixel_pts) > 1:
        # Dark outline for contrast
        draw.line(pixel_pts, fill=(15, 30, 60), width=6)
        # Bright cyan route line
        draw.line(pixel_pts, fill=(0, 200, 255), width=4)

    # Start = Green, End = Red
    def draw_pin(pt, color):
        r = 6
        draw.ellipse([pt[0] - r - 1, pt[1] - r - 1, pt[0] + r + 1, pt[1] + r + 1], fill=(255, 255, 255))
        draw.ellipse([pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r], fill=color)

    draw_pin(pixel_pts[0], (0, 200, 60))
    draw_pin(pixel_pts[-1], (230, 40, 40))

    crop_box = (
        crop_x0 - min_tx * 256,
        crop_y0 - min_ty * 256,
        crop_x1 - min_tx * 256,
        crop_y1 - min_ty * 256,
    )
    final_img = canvas.crop(crop_box)

    # Tiny attribution tag
    f_draw = ImageDraw.Draw(final_img)
    f_draw.text((target_w - 38, target_h - 11), "© OSM", fill=(100, 100, 100))

    buf = BytesIO()
    final_img.save(buf, format="PNG")
    return buf.getvalue()


def render_point_map(lat, lon, target_w=240, target_h=180, zoom=15):
    c_x, c_y = lat_lon_to_xy(lat, lon, zoom)
    c_px = c_x * 256
    c_py = c_y * 256

    crop_x0 = int(c_px - target_w / 2)
    crop_y0 = int(c_py - target_h / 2)
    crop_x1 = crop_x0 + target_w
    crop_y1 = crop_y0 + target_h

    min_tx = crop_x0 // 256
    max_tx = crop_x1 // 256
    min_ty = crop_y0 // 256
    max_ty = crop_y1 // 256

    canvas_w = (max_tx - min_tx + 1) * 256
    canvas_h = (max_ty - min_ty + 1) * 256
    canvas = Image.new("RGB", (canvas_w, canvas_h), (215, 220, 225))

    for tx in range(min_tx, max_tx + 1):
        for ty in range(min_ty, max_ty + 1):
            tile_bytes = fetch_tile(zoom, tx, ty)
            if tile_bytes:
                try:
                    t_img = Image.open(BytesIO(tile_bytes)).convert("RGB")
                    canvas.paste(t_img, ((tx - min_tx) * 256, (ty - min_ty) * 256))
                except Exception:
                    pass

    draw = ImageDraw.Draw(canvas)
    center_px = int(c_px - min_tx * 256)
    center_py = int(c_py - min_ty * 256)

    # Draw pin marker
    r = 7
    draw.ellipse([center_px - r - 1, center_py - r - 1, center_px + r + 1, center_py + r + 1], fill=(255, 255, 255))
    draw.ellipse([center_px - r, center_py - r, center_px + r, center_py + r], fill=(230, 40, 40))

    crop_box = (
        crop_x0 - min_tx * 256,
        crop_y0 - min_ty * 256,
        crop_x1 - min_tx * 256,
        crop_y1 - min_ty * 256,
    )
    final_img = canvas.crop(crop_box)

    f_draw = ImageDraw.Draw(final_img)
    f_draw.text((target_w - 38, target_h - 11), "© OSM", fill=(100, 100, 100))

    buf = BytesIO()
    final_img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# UI & CSS
# ---------------------------------------------------------------------------
MAPS_CSS = """
.maps-form{background:#0f1620;border:1px solid #263241;padding:8px;border-radius:3px;margin:6px 0;}
.maps-form label{display:block;color:#91a0af;font-size:11px;margin:5px 0 2px;}
.maps-form input[type=text]{width:100%;box-sizing:border-box;background:#fff;color:#000;border:0;padding:5px;font-size:12px;margin-bottom:3px;}
.maps-form select{width:100%;box-sizing:border-box;background:#fff;color:#000;border:0;padding:5px;font-size:12px;margin-bottom:6px;}
.maps-form input[type=submit]{background:#95e1ff;color:#000;border:0;padding:6px 14px;font-size:12px;font-weight:bold;margin-top:4px;cursor:pointer;}
.map-wrap{text-align:center;margin:6px 0;}
.map-img{display:block;margin:0 auto;max-width:100%;height:auto;border:1px solid #263241;border-radius:2px;}
.route-summary{background:#0f1620;border:1px solid #263241;padding:6px 8px;margin:6px 0;border-radius:3px;font-size:12px;}
.route-meta{color:#9fdfff;font-weight:bold;margin-bottom:3px;}
.route-pts{font-size:11px;color:#91a0af;line-height:1.35;}
.route-pts strong{color:#fff;}
.steps-box{border-top:1px solid #263241;margin-top:8px;padding-top:6px;}
.steps-title{font-size:12px;font-weight:bold;color:#9fdfff;margin-bottom:6px;}
ol.steps-list{margin:0;padding-left:18px;font-size:12px;line-height:1.45;}
ol.steps-list li{margin-bottom:5px;color:#fff;}
.recent-box{margin-top:10px;border-top:1px solid #263241;padding-top:6px;}
.recent-title{font-size:11px;color:#91a0af;font-weight:bold;margin-bottom:4px;}
.recent-item{background:#0f1620;border:1px solid #263241;padding:4px 6px;margin:3px 0;border-radius:2px;}
.recent-item a{display:block;font-size:11px;color:#9fdfff;text-decoration:none;}
.err-box{background:#3b1414;border:1px solid #752727;color:#ff9e9e;padding:6px 8px;font-size:12px;margin:6px 0;border-radius:3px;}
"""


# ---------------------------------------------------------------------------
# Flask Routes
# ---------------------------------------------------------------------------
def register_maps_routes(flask_app, prefix="/maps"):
    base = prefix.rstrip("/")

    @flask_app.route(base)
    def maps_index():
        from_val = request.args.get("from", "").strip()
        to_val = request.args.get("to", "").strip()
        mode_val = request.args.get("mode", "foot").strip()

        # Fetch recent routes
        conn = connect_db()
        recent = conn.execute(
            "SELECT from_name, to_name, from_query, to_query, mode FROM recent_routes ORDER BY id DESC LIMIT 5"
        ).fetchall()
        conn.close()

        recent_html = ""
        if recent:
            recent_html = "<div class='recent-box'><div class='recent-title'>Recent Searches</div>"
            for r in recent:
                r_url = f"{base}/directions?from={h(r['from_query'])}&to={h(r['to_query'])}&mode={h(r['mode'])}"
                m_tag = "W" if r["mode"] == "foot" else ("D" if r["mode"] == "driving" else "C")
                recent_html += f"""
<div class='recent-item'>
    <a href='{h(r_url)}'>[{m_tag}] {h(r['from_name'])} -> {h(r['to_name'])}</a>
</div>
"""
            recent_html += "</div>"

        body = f"""
<form class="maps-form" method="get" action="{base}/directions">
    <div style="font-weight:bold;color:#9fdfff;margin-bottom:4px;">Directions</div>
    <label>Current Location / Origin</label>
    <input type="text" name="from" value="{h(from_val)}" placeholder="Name or Lat,Lon (e.g. 51.5033, -0.1195)" required>
    
    <label>Destination</label>
    <input type="text" name="to" value="{h(to_val)}" placeholder="Name or Lat,Lon (e.g. 51.5007, -0.1246)" required>
    
    <label>Travel Mode</label>
    <select name="mode">
        <option value="foot"{' selected' if mode_val == 'foot' else ''}>[W] Walking</option>
        <option value="driving"{' selected' if mode_val == 'driving' else ''}>[D] Driving</option>
        <option value="bike"{' selected' if mode_val == 'bike' else ''}>[C] Cycling</option>
    </select>
    
    <div>
        <input type="submit" value="Get Directions">
    </div>
</form>

<form class="maps-form" method="get" action="{base}/place" style="margin-top:8px;">
    <div style="font-weight:bold;color:#9fdfff;margin-bottom:4px;">View Location or Coords</div>
    <input type="text" name="q" placeholder="e.g. Eiffel Tower or 48.8584, 2.2945" required>
    <div>
        <input type="submit" value="Show on Map">
    </div>
</form>
{recent_html}
"""
        return phone_page("", body, nav=[("Apps", "/")], extra_css=MAPS_CSS)

    @flask_app.route(base + "/directions")
    def maps_directions():
        from_q = request.args.get("from", "").strip()
        to_q = request.args.get("to", "").strip()
        mode = request.args.get("mode", "foot").strip()
        if mode not in ("foot", "driving", "bike"):
            mode = "foot"

        if not from_q or not to_q:
            return redirect(base)

        # Geocode start
        from_res = geocode_location(from_q)
        if not from_res:
            body = f"""
<div class="err-box">Could not find location: <strong>{h(from_q)}</strong></div>
<p><a class="btn" href="{base}?from={h(from_q)}&to={h(to_q)}&mode={h(mode)}">Edit Search</a></p>
"""
            return phone_page("Maps", body, nav=[("Apps", "/"), ("Maps", base)], extra_css=MAPS_CSS)

        # Geocode destination
        to_res = geocode_location(to_q)
        if not to_res:
            body = f"""
<div class="err-box">Could not find destination: <strong>{h(to_q)}</strong></div>
<p><a class="btn" href="{base}?from={h(from_q)}&to={h(to_q)}&mode={h(mode)}">Edit Search</a></p>
"""
            return phone_page("Maps", body, nav=[("Apps", "/"), ("Maps", base)], extra_css=MAPS_CSS)

        lat1, lon1, name1 = from_res
        lat2, lon2, name2 = to_res

        route_key = f"{mode}:{lat1:.5f},{lon1:.5f}:{lat2:.5f},{lon2:.5f}"
        route_id = hashlib.md5(route_key.encode("utf-8")).hexdigest()[:12]

        conn = connect_db()
        cached = conn.execute("SELECT * FROM routes_cache WHERE id = ?", (route_id,)).fetchone()

        if cached:
            distance = cached["distance"]
            duration = cached["duration"]
            steps = json.loads(cached["steps_json"])
            coords = json.loads(cached["coords_json"])
        else:
            route_data = fetch_osrm_route(lon1, lat1, lon2, lat2, mode=mode)
            if not route_data or not route_data.get("steps"):
                conn.close()
                body = f"""
<div class="err-box">No route found between <strong>{h(name1)}</strong> and <strong>{h(name2)}</strong>.</div>
<p><a class="btn" href="{base}?from={h(from_q)}&to={h(to_q)}&mode={h(mode)}">Try Different Route</a></p>
"""
                return phone_page("Maps", body, nav=[("Apps", "/"), ("Maps", base)], extra_css=MAPS_CSS)

            distance = route_data["distance"]
            duration = route_data["duration"]
            steps = route_data["steps"]
            coords = route_data["coords"]

            conn.execute(
                """
                INSERT OR REPLACE INTO routes_cache 
                (id, from_query, to_query, from_name, to_name, mode, distance, duration, steps_json, coords_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    route_id,
                    from_q,
                    to_q,
                    name1,
                    name2,
                    mode,
                    distance,
                    duration,
                    json.dumps(steps),
                    json.dumps(coords),
                    time.time(),
                ),
            )
            # Log in recent routes
            conn.execute(
                "INSERT INTO recent_routes (from_name, to_name, from_query, to_query, mode, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (name1, name2, from_q, to_q, mode, time.time()),
            )
            conn.commit()

        conn.close()

        # Format distance & duration
        if distance < 1000:
            dist_str = f"{int(round(distance))} m"
        else:
            dist_str = f"{distance / 1000.0:.1f} km"

        mins = int(round(duration / 60.0))
        if mins < 60:
            time_str = f"~{mins} min" if mins > 0 else "< 1 min"
        else:
            hrs = mins // 60
            rem_m = mins % 60
            time_str = f"~{hrs}h {rem_m}m"

        mode_name = "Walking [W]" if mode == "foot" else ("Driving [D]" if mode == "driving" else "Cycling [C]")
        reverse_url = f"{base}/directions?from={h(to_q)}&to={h(from_q)}&mode={h(mode)}"

        # Format steps list
        steps_html = "<ol class='steps-list'>"
        for s in steps:
            steps_html += f"<li>{h(s['instruction'])}</li>"
        steps_html += "</ol>"

        body = f"""
<div class="route-summary">
    <div class="route-meta">{dist_str} | {time_str} ({mode_name})</div>
    <div class="route-pts">
        <div><strong>From:</strong> {h(name1)}</div>
        <div><strong>To:</strong> {h(name2)}</div>
    </div>
</div>

<div class="map-wrap">
    <img class="map-img" src="{base}/render?id={route_id}" width="240" height="180" alt="Route Map">
</div>

<p style="margin:6px 0;">
    <a class="btn" href="{h(reverse_url)}">Reverse</a>
    <a class="btn" href="{base}?from={h(from_q)}&to={h(to_q)}&mode={h(mode)}">Edit</a>
    <a class="btn" href="{base}">New</a>
</p>

<div class="steps-box">
    <div class="steps-title">Turn-by-Turn Directions</div>
    {steps_html}
</div>
"""
        return phone_page("", body, nav=[("Apps", "/"), ("Maps", base), ("Back", base)], extra_css=MAPS_CSS)

    @flask_app.route(base + "/render")
    def maps_render():
        route_id = request.args.get("id", "").strip()
        if route_id:
            conn = connect_db()
            row = conn.execute("SELECT coords_json FROM routes_cache WHERE id = ?", (route_id,)).fetchone()
            conn.close()
            if row:
                coords = json.loads(row["coords_json"])
                png_bytes = render_route_map(coords, target_w=240, target_h=180)
                resp = Response(png_bytes, mimetype="image/png")
                resp.headers["Cache-Control"] = "public, max-age=86400"
                return resp

        # Single point view fallback
        lat_arg = request.args.get("lat")
        lon_arg = request.args.get("lon")
        if lat_arg and lon_arg:
            try:
                lat = float(lat_arg)
                lon = float(lon_arg)
                png_bytes = render_point_map(lat, lon, target_w=240, target_h=180)
                resp = Response(png_bytes, mimetype="image/png")
                resp.headers["Cache-Control"] = "public, max-age=86400"
                return resp
            except ValueError:
                pass

        blank = Image.new("RGB", (240, 180), (30, 40, 55))
        buf = BytesIO()
        blank.save(buf, format="PNG")
        return Response(buf.getvalue(), mimetype="image/png")

    @flask_app.route(base + "/place")
    def maps_place():
        q = request.args.get("q", "").strip()
        if not q:
            return redirect(base)

        res = geocode_location(q)
        if not res:
            body = f"""
<div class="err-box">Could not find location: <strong>{h(q)}</strong></div>
<p><a class="btn" href="{base}">Back to Search</a></p>
"""
            return phone_page("Maps", body, nav=[("Apps", "/"), ("Maps", base)], extra_css=MAPS_CSS)

        lat, lon, name = res
        body = f"""
<div class="route-summary">
    <div class="route-meta">{h(name)}</div>
    <div class="route-pts">Coords: {lat:.5f}, {lon:.5f}</div>
</div>

<div class="map-wrap">
    <img class="map-img" src="{base}/render?lat={lat}&lon={lon}" width="240" height="180" alt="Place Map">
</div>

<p style="margin:8px 0;">
    <a class="btn" href="{base}?from={lat:.5f},{lon:.5f}">Directions From Here</a>
    <a class="btn" href="{base}?to={lat:.5f},{lon:.5f}">Directions To Here</a>
    <a class="btn" href="{base}">New Search</a>
</p>
"""
        return phone_page("", body, nav=[("Apps", "/"), ("Maps", base), ("Back", base)], extra_css=MAPS_CSS)
