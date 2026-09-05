import calendar as py_calendar
import os
import sqlite3
import time
from datetime import date, datetime

from flask import redirect, request
from ui import h, phone_page

BASE_DIR = os.path.dirname(__file__)
CALENDAR_DB_PATH = os.environ.get("CALENDAR_DB_PATH", os.path.join(BASE_DIR, "calendar.db"))


def connect_db():
    conn = sqlite3.connect(CALENDAR_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_calendar_db():
    conn = connect_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            date TEXT NOT NULL,
            time TEXT DEFAULT '',
            created_at REAL NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_date ON events(date)")
    conn.commit()
    conn.close()


init_calendar_db()


def get_events_for_month(year, month):
    prefix = f"{year:04d}-{month:02d}-%"
    conn = connect_db()
    rows = conn.execute("SELECT DISTINCT date FROM events WHERE date LIKE ?", (prefix,)).fetchall()
    conn.close()
    return {r["date"] for r in rows}


def get_events_for_date(date_str):
    conn = connect_db()
    rows = conn.execute(
        "SELECT id, title, description, date, time FROM events WHERE date = ? ORDER BY time ASC, id ASC",
        (date_str,),
    ).fetchall()
    conn.close()
    return rows


def get_event(event_id):
    conn = connect_db()
    row = conn.execute(
        "SELECT id, title, description, date, time FROM events WHERE id = ?",
        (event_id,),
    ).fetchone()
    conn.close()
    return row


def get_upcoming_events(limit=30):
    today_str = date.today().isoformat()
    conn = connect_db()
    rows = conn.execute(
        "SELECT id, title, description, date, time FROM events WHERE date >= ? ORDER BY date ASC, time ASC LIMIT ?",
        (today_str, limit),
    ).fetchall()
    conn.close()
    return rows


CALENDAR_CSS = """
.cal-bar{display:flex;justify-content:space-between;align-items:center;margin:3px 0 6px;padding:3px 0;border-bottom:1px solid #263241;}
.cal-bar a{color:#9fdfff;font-size:12px;font-weight:bold;padding:2px 4px;}
.cal-title{font-size:13px;font-weight:bold;color:#fff;}
.cal-subnav{text-align:center;margin:0 0 6px;font-size:11px;}
.cal-subnav a{color:#ffd35a;margin:0 6px;}
.cal-grid{width:100%;table-layout:fixed;border-collapse:collapse;text-align:center;margin-bottom:6px;}
.cal-grid th{padding:2px 0;font-size:10px;color:#91a0af;text-align:center;}
.cal-grid td{padding:0;height:24px;border:1px solid #263241;text-align:center;vertical-align:middle;}
.cal-grid td.empty{background:#111622;border-color:#1c2533;}
.cal-grid td a{display:block;width:100%;height:24px;line-height:24px;color:#fff;text-decoration:none;font-size:11px;}
.cal-grid td.today a{color:#ffd35a;font-weight:bold;}
.cal-grid td.selected{background:#234268;}
.cal-grid td.selected a{color:#fff;font-weight:bold;}
.cal-grid td.has-event{position:relative;}
.cal-grid td.has-event a::after{content:'•';position:absolute;bottom:-7px;left:0;right:0;font-size:13px;color:#95e1ff;line-height:1;}
.cal-day-box{border-top:1px solid #263241;padding-top:6px;margin-top:4px;}
.day-header{font-size:12px;font-weight:bold;color:#9fdfff;margin-bottom:4px;}
.event-row{background:#0f1620;border:1px solid #263241;padding:5px 6px;margin:3px 0;border-radius:2px;}
.event-row a{color:#fff;display:block;font-size:12px;text-decoration:none;}
.event-row .time{color:#ffd35a;font-size:10px;margin-bottom:1px;}
.event-row .desc{color:#91a0af;font-size:10px;margin-top:2px;}
.btn{display:inline-block;background:#263241;color:#95e1ff;border:1px solid #3b4d61;padding:4px 10px;font-size:11px;text-decoration:none;border-radius:3px;margin:4px 0;}
.btn-danger{background:#5c1d1d;color:#ff9e9e;border-color:#852b2b;}
.err{color:#ff8b8b;font-size:12px;margin:4px 0;}
form label{display:block;color:#91a0af;font-size:11px;margin:6px 0 2px;}
input[type=text], textarea{width:100%;box-sizing:border-box;background:#fff;color:#000;border:0;padding:5px;font-size:12px;margin-bottom:4px;}
textarea{height:54px;resize:vertical;}
input[type=submit]{background:#95e1ff;color:#000;border:0;padding:5px 12px;font-size:12px;font-weight:bold;margin-top:4px;}
"""


def parse_year_month(y_val, m_val):
    today = date.today()
    try:
        y = int(y_val)
        m = int(m_val)
        if m < 1 or m > 12 or y < 1970 or y > 2100:
            return today.year, today.month
        return y, m
    except Exception:
        return today.year, today.month


def format_nice_date(date_str):
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return d.strftime("%A, %b %d, %Y")
    except Exception:
        return date_str


def register_calendar_routes(flask_app, prefix="/calendar"):
    base = prefix.rstrip("/")

    @flask_app.route(base)
    @flask_app.route(base + "/")
    def calendar_index():
        today = date.today()
        today_str = today.isoformat()

        req_d = request.args.get("d", "").strip()
        y_arg = request.args.get("y")
        m_arg = request.args.get("m")

        if req_d:
            try:
                parsed_d = datetime.strptime(req_d, "%Y-%m-%d").date()
                selected_d = req_d
                if y_arg is None or m_arg is None:
                    year, month = parsed_d.year, parsed_d.month
                else:
                    year, month = parse_year_month(y_arg, m_arg)
            except Exception:
                selected_d = today_str
                year, month = parse_year_month(y_arg, m_arg)
        else:
            year, month = parse_year_month(y_arg, m_arg)
            if year == today.year and month == today.month:
                selected_d = today_str
            else:
                selected_d = f"{year:04d}-{month:02d}-01"

        if month == 1:
            prev_y, prev_m = year - 1, 12
        else:
            prev_y, prev_m = year, month - 1

        if month == 12:
            next_y, next_m = year + 1, 1
        else:
            next_y, next_m = year, month + 1

        month_name = py_calendar.month_name[month]
        dates_with_events = get_events_for_month(year, month)
        weeks = py_calendar.monthcalendar(year, month)

        prev_url = f"{base}?y={prev_y}&m={prev_m}&d={selected_d}"
        next_url = f"{base}?y={next_y}&m={next_m}&d={selected_d}"

        body = f"""
<div class="cal-bar">
    <a href="{h(prev_url)}">&laquo; Prev</a>
    <span class="cal-title">{month_name} {year}</span>
    <a href="{h(next_url)}">Next &raquo;</a>
</div>
<div class="cal-subnav">
    <a href="{base}?d={today_str}">[Today]</a>
    <a href="{base}/agenda">[Agenda]</a>
</div>
<table class="cal-grid">
    <thead>
        <tr>
            <th>Mo</th><th>Tu</th><th>We</th><th>Th</th><th>Fr</th><th>Sa</th><th>Su</th>
        </tr>
    </thead>
    <tbody>
"""
        for week in weeks:
            body += "<tr>"
            for day in week:
                if day == 0:
                    body += "<td class='empty'>&nbsp;</td>"
                else:
                    cell_d = f"{year:04d}-{month:02d}-{day:02d}"
                    cls = []
                    if cell_d == today_str:
                        cls.append("today")
                    if cell_d == selected_d:
                        cls.append("selected")
                    if cell_d in dates_with_events:
                        cls.append("has-event")
                    cls_attr = f" class='{' '.join(cls)}'" if cls else ""
                    day_url = f"{base}?y={year}&m={month}&d={cell_d}"
                    body += f"<td{cls_attr}><a href='{h(day_url)}'>{day}</a></td>"
            body += "</tr>\n"

        body += "</tbody></table>"

        events = get_events_for_date(selected_d)
        nice_date = format_nice_date(selected_d)
        add_url = f"{base}/add?d={selected_d}&y={year}&m={month}"

        body += f"""
<div class="cal-day-box">
    <div class="day-header">{h(nice_date)}</div>
"""
        if events:
            for ev in events:
                ev_url = f"{base}/event/{ev['id']}?d={selected_d}&y={year}&m={month}"
                time_str = h(ev["time"]) if ev["time"] else "All day"
                body += f"""
    <div class="event-row">
        <div class="time">{time_str}</div>
        <a href="{h(ev_url)}"><strong>{h(ev['title'])}</strong></a>
"""
                if ev["description"]:
                    body += f"<div class='desc'>{h(ev['description'])}</div>"
                body += "</div>"
        else:
            body += "<div class='muted small'>No events for this date.</div>"

        body += f"""
    <div><a class="btn" href="{h(add_url)}">+ Add Event</a></div>
</div>
"""
        return phone_page("", body, nav=[("Apps", "/")], extra_css=CALENDAR_CSS)

    @flask_app.route(base + "/add", methods=["GET", "POST"])
    def calendar_add():
        y = request.args.get("y", "")
        m = request.args.get("m", "")
        def_date = request.args.get("d", date.today().isoformat())
        back_url = f"{base}?d={def_date}"
        if y and m:
            back_url += f"&y={y}&m={m}"

        error = ""
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            ev_date = request.form.get("date", "").strip()
            ev_time = request.form.get("time", "").strip()
            desc = request.form.get("description", "").strip()

            if not title:
                error = "Title is required"
            elif not ev_date:
                error = "Date is required (YYYY-MM-DD)"
            else:
                try:
                    parsed = datetime.strptime(ev_date, "%Y-%m-%d").date()
                    ev_date = parsed.isoformat()
                    conn = connect_db()
                    conn.execute(
                        "INSERT INTO events (title, description, date, time, created_at) VALUES (?, ?, ?, ?, ?)",
                        (title, desc, ev_date, ev_time, time.time()),
                    )
                    conn.commit()
                    conn.close()
                    return redirect(f"{base}?d={ev_date}&y={parsed.year}&m={parsed.month}")
                except ValueError:
                    error = "Invalid date format. Use YYYY-MM-DD"

        body = f"""
<h3>New Event</h3>
"""
        if error:
            body += f"<div class='err'>{h(error)}</div>"

        body += f"""
<form method="post" action="{base}/add?d={h(def_date)}&y={h(y)}&m={h(m)}">
    <label>Title *</label>
    <input type="text" name="title" value="" required autofocus>
    <label>Date (YYYY-MM-DD) *</label>
    <input type="text" name="date" value="{h(def_date)}" required>
    <label>Time (optional, e.g. 14:30)</label>
    <input type="text" name="time" value="" placeholder="HH:MM">
    <label>Description (optional)</label>
    <textarea name="description"></textarea>
    <div><input type="submit" value="Save Event"></div>
</form>
<p><a class="btn" href="{h(back_url)}">Cancel</a></p>
"""
        return phone_page("New Event", body, nav=[("Apps", "/"), ("Calendar", base), ("Back", back_url)], extra_css=CALENDAR_CSS)

    @flask_app.route(base + "/event/<int:event_id>", methods=["GET", "POST"])
    def calendar_event_detail(event_id):
        ev = get_event(event_id)
        if not ev:
            return phone_page("Not Found", "<div class='err'>Event not found.</div>", nav=[("Apps", "/"), ("Calendar", base)]), 404

        back_url = f"{base}?d={ev['date']}"
        error = ""

        if request.method == "POST":
            title = request.form.get("title", "").strip()
            ev_date = request.form.get("date", "").strip()
            ev_time = request.form.get("time", "").strip()
            desc = request.form.get("description", "").strip()

            if not title:
                error = "Title is required"
            elif not ev_date:
                error = "Date is required (YYYY-MM-DD)"
            else:
                try:
                    parsed = datetime.strptime(ev_date, "%Y-%m-%d").date()
                    ev_date = parsed.isoformat()
                    conn = connect_db()
                    conn.execute(
                        "UPDATE events SET title = ?, description = ?, date = ?, time = ? WHERE id = ?",
                        (title, desc, ev_date, ev_time, event_id),
                    )
                    conn.commit()
                    conn.close()
                    return redirect(f"{base}?d={ev_date}&y={parsed.year}&m={parsed.month}")
                except ValueError:
                    error = "Invalid date format. Use YYYY-MM-DD"

        body = f"""
<h3>Edit Event</h3>
"""
        if error:
            body += f"<div class='err'>{h(error)}</div>"

        body += f"""
<form method="post" action="{base}/event/{event_id}">
    <label>Title *</label>
    <input type="text" name="title" value="{h(ev['title'])}" required>
    <label>Date (YYYY-MM-DD) *</label>
    <input type="text" name="date" value="{h(ev['date'])}" required>
    <label>Time (optional)</label>
    <input type="text" name="time" value="{h(ev['time'])}" placeholder="HH:MM">
    <label>Description</label>
    <textarea name="description">{h(ev['description'])}</textarea>
    <div><input type="submit" value="Save Changes"></div>
</form>

<p style="margin-top:12px;">
    <a class="btn btn-danger" href="{base}/event/{event_id}/delete">Delete Event</a>
    <a class="btn" href="{h(back_url)}">Cancel</a>
</p>
"""
        return phone_page("Event", body, nav=[("Apps", "/"), ("Calendar", base), ("Back", back_url)], extra_css=CALENDAR_CSS)

    @flask_app.route(base + "/event/<int:event_id>/delete", methods=["GET", "POST"])
    def calendar_delete(event_id):
        ev = get_event(event_id)
        if not ev:
            return redirect(base)
        redirect_date = ev["date"]
        if request.method == "POST":
            conn = connect_db()
            conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
            conn.commit()
            conn.close()
            return redirect(f"{base}?d={redirect_date}")

        time_str = h(ev["time"]) if ev["time"] else "All day"
        back_url = f"{base}/event/{event_id}"
        body = f"""
<p>Delete event?</p>
<div class="event-row">
    <div class="time">{time_str}</div>
    <strong>{h(ev['title'])}</strong>
    <div class="desc">{h(ev['date'])}</div>
</div>
<form method="post" action="{base}/event/{event_id}/delete" style="margin-top:10px;">
    <input class="btn btn-danger" type="submit" value="Delete Event">
    <a class="btn" href="{h(back_url)}">Cancel</a>
</form>
"""
        return phone_page("Delete Event", body, nav=[("Apps", "/"), ("Calendar", base), ("Back", back_url)], extra_css=CALENDAR_CSS)

    @flask_app.route(base + "/agenda")
    def calendar_agenda():
        events = get_upcoming_events(limit=40)
        body = "<h3>Upcoming Events</h3>"
        if events:
            current_group = None
            for ev in events:
                if ev["date"] != current_group:
                    current_group = ev["date"]
                    body += f"<div class='day-header' style='margin-top:10px;'>{h(format_nice_date(current_group))}</div>"
                ev_url = f"{base}/event/{ev['id']}"
                time_str = h(ev["time"]) if ev["time"] else "All day"
                body += f"""
<div class="event-row">
    <div class="time">{time_str}</div>
    <a href="{h(ev_url)}"><strong>{h(ev['title'])}</strong></a>
"""
                if ev["description"]:
                    body += f"<div class='desc'>{h(ev['description'])}</div>"
                body += "</div>"
        else:
            body += "<div class='muted small'>No upcoming events found.</div>"

        body += f"<p><a class='btn' href='{base}'>&laquo; Back to Month Grid</a></p>"
        return phone_page("Agenda", body, nav=[("Apps", "/"), ("Calendar", base)], extra_css=CALENDAR_CSS)
