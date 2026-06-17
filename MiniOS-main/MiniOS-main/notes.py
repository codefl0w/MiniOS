import os
import sqlite3
import time
from datetime import datetime

from env_loader import load_env
from flask import redirect, request
from ui import h, phone_page

load_env()

BASE_DIR = os.path.dirname(__file__)
NOTES_DB_PATH = os.environ.get("NOTES_DB_PATH", os.path.join(BASE_DIR, "notes.db"))


def connect_db():
    conn = sqlite3.connect(NOTES_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_notes_db():
    conn = connect_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            body TEXT NOT NULL,
            created REAL NOT NULL,
            updated REAL NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def add_note(body):
    now = time.time()
    conn = connect_db()
    cur = conn.execute(
        "INSERT INTO notes (body, created, updated) VALUES (?, ?, ?)",
        (body, now, now),
    )
    conn.commit()
    note_id = cur.lastrowid
    conn.close()
    return note_id


def update_note(note_id, body):
    conn = connect_db()
    conn.execute("UPDATE notes SET body=?, updated=? WHERE id=?", (body, time.time(), note_id))
    conn.commit()
    conn.close()


def delete_note(note_id):
    conn = connect_db()
    conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
    conn.commit()
    conn.close()


def get_note(note_id):
    conn = connect_db()
    row = conn.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
    conn.close()
    return row


def list_notes(query=""):
    conn = connect_db()
    if query:
        rows = conn.execute(
            "SELECT * FROM notes WHERE body LIKE ? ORDER BY updated DESC LIMIT 50",
            (f"%{query}%",),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM notes ORDER BY updated DESC LIMIT 50").fetchall()
    conn.close()
    return rows


def format_time(ts):
    return datetime.fromtimestamp(ts).strftime("%d.%m %H:%M")


def note_title(body):
    for line in body.splitlines():
        line = line.strip()
        if line:
            return line[:36]
    return "Untitled"


def note_preview(body):
    text = " ".join(body.split())
    if len(text) > 70:
        return text[:67] + "..."
    return text


NOTES_CSS = """
form{margin:0 0 8px;}
input[type=text],textarea{width:100%;box-sizing:border-box;background:#ffffff;color:#000;border:0;padding:6px;font-size:13px;font-family:Arial;}
textarea{height:132px;}
input[type=submit],button{background:#95e1ff;color:#000;border:0;padding:6px 8px;font-size:13px;}
.row{display:block;border-top:1px solid #263241;padding:7px 0;color:#fff;}
.small{display:block;color:#91a0af;font-size:11px;margin-top:2px;}
.actions{margin-top:7px;}
.danger{background:#ff8b8b;color:#000;}
"""


def register_notes_routes(flask_app, prefix="/notes"):
    init_notes_db()
    base = prefix.rstrip("/")

    @flask_app.route(base)
    @flask_app.route(base + "/")
    def notes_index():
        query = request.args.get("q", "").strip()
        rows = list_notes(query)
        body = f"""
<form method="get" action="{base}">
<input type="text" name="q" value="{h(query)}" placeholder="Search">
<input type="submit" value="Go">
</form>
<p><a href="{base}/new">New note</a></p>
"""
        if not rows:
            body += "<p class='muted'>No notes</p>"
        for row in rows:
            body += (
                f"<a class='row' href='{base}/{row['id']}'><strong>{h(note_title(row['body']))}</strong>"
                f"<span class='small'>{h(note_preview(row['body']))}</span>"
                f"<span class='small'>{h(format_time(row['updated']))}</span></a>"
            )
        return phone_page("Notes", body, nav=[("Apps", "/")], extra_css=NOTES_CSS)

    @flask_app.route(base + "/new", methods=["GET", "POST"])
    def notes_new():
        if request.method == "POST":
            body = request.form.get("body", "").strip()
            if body:
                note_id = add_note(body)
                return redirect(f"{base}/{note_id}")
        form = f"""
<form method="post" action="{base}/new">
<textarea name="body"></textarea>
<div class="actions"><input type="submit" value="Save"></div>
</form>
"""
        return phone_page("New Note", form, nav=[("Apps", "/"), ("Notes", base)], extra_css=NOTES_CSS)

    @flask_app.route(base + "/<int:note_id>", methods=["GET", "POST"])
    def notes_detail(note_id):
        row = get_note(note_id)
        if not row:
            return phone_page("Not Found", "<p class='muted'>Note missing</p>", nav=[("Notes", base)]), 404
        if request.method == "POST":
            body = request.form.get("body", "").strip()
            if body:
                update_note(note_id, body)
            return redirect(f"{base}/{note_id}")

        form = f"""
<form method="post" action="{base}/{note_id}">
<textarea name="body">{h(row['body'])}</textarea>
<div class="actions"><input type="submit" value="Save"></div>
</form>
<form method="post" action="{base}/{note_id}/delete">
<input class="danger" type="submit" value="Delete">
</form>
<p class="small">Updated {h(format_time(row['updated']))}</p>
"""
        return phone_page("Edit Note", form, nav=[("Apps", "/"), ("Notes", base)], extra_css=NOTES_CSS)

    @flask_app.route(base + "/<int:note_id>/delete", methods=["POST"])
    def notes_delete(note_id):
        delete_note(note_id)
        return redirect(base)
