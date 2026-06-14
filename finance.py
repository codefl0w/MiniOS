import os
import sqlite3
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from env_loader import load_env
from flask import redirect, request
from settings import app_settings
from ui import h, phone_page

load_env()

BASE_DIR = os.path.dirname(__file__)
FINANCE_DB_PATH = os.environ.get("FINANCE_DB_PATH", os.path.join(BASE_DIR, "finance.db"))


def currency():
    return app_settings("finance")["currency"]


def connect_db():
    conn = sqlite3.connect(FINANCE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_finance_db():
    conn = connect_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS finance_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item TEXT NOT NULL,
            price_cents INTEGER NOT NULL,
            created REAL NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def parse_price(value):
    cur = currency()
    text = (value or "").strip().replace(cur, "").replace(cur.lower(), "").replace("tl", "").replace("TL", "")
    text = text.replace(" ", "").replace(",", ".")
    if not text:
        raise ValueError("missing price")
    try:
        amount = Decimal(text).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError("bad price") from exc
    if amount < 0:
        raise ValueError("negative price")
    return int(amount * 100)


def money(cents):
    amount = Decimal(cents) / Decimal(100)
    return f"{amount:.2f} {currency()}"


def add_entry(item, price_cents):
    conn = connect_db()
    conn.execute(
        "INSERT INTO finance_entries (item, price_cents, created) VALUES (?, ?, ?)",
        (item, price_cents, time.time()),
    )
    conn.commit()
    conn.close()


def delete_entry(entry_id):
    conn = connect_db()
    conn.execute("DELETE FROM finance_entries WHERE id=?", (entry_id,))
    conn.commit()
    conn.close()


def get_entry(entry_id):
    conn = connect_db()
    row = conn.execute("SELECT * FROM finance_entries WHERE id=?", (entry_id,)).fetchone()
    conn.close()
    return row


def list_entries(limit=100):
    conn = connect_db()
    rows = conn.execute(
        "SELECT * FROM finance_entries ORDER BY created DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return rows


def totals():
    day_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    conn = connect_db()
    grand = conn.execute("SELECT COALESCE(SUM(price_cents), 0) FROM finance_entries").fetchone()[0]
    today = conn.execute(
        "SELECT COALESCE(SUM(price_cents), 0) FROM finance_entries WHERE created >= ?",
        (day_start,),
    ).fetchone()[0]
    count = conn.execute("SELECT COUNT(*) FROM finance_entries").fetchone()[0]
    conn.close()
    return {"grand": grand, "today": today, "count": count}


def date_short(ts):
    return datetime.fromtimestamp(ts).strftime("%d.%m")


FINANCE_CSS = """
form{margin:0 0 8px;}
input[type=text]{width:100%;box-sizing:border-box;background:#fff;color:#000;border:0;padding:6px;font-size:13px;margin:0 0 4px;}
input[type=submit]{background:#95e1ff;color:#000;border:0;padding:6px 8px;font-size:13px;}
.total{background:#0f1620;border:1px solid #263241;padding:6px;margin:6px 0;}
.total strong{color:#ffd35a;font-size:15px;}
.small{color:#91a0af;font-size:11px;}
table{width:100%;border-collapse:collapse;font-size:12px;}
th{color:#91a0af;text-align:left;border-bottom:1px solid #263241;padding:4px 2px;}
td{border-bottom:1px solid #263241;padding:5px 2px;vertical-align:top;}
.price{text-align:right;white-space:nowrap;color:#ffd35a;}
.del{text-align:right;width:18px;}
.del a{color:#ff8b8b;}
.danger{background:#ff8b8b;color:#000;}
"""


def register_finance_routes(flask_app, prefix="/finance"):
    init_finance_db()
    base = prefix.rstrip("/")

    @flask_app.route(base)
    @flask_app.route(base + "/")
    def finance_index():
        rows = list_entries()
        total = totals()
        err = request.args.get("err")

        body = f"""
<form method="post" action="{base}/add">
<input type="text" name="item" placeholder="Item">
<input type="text" name="price" placeholder="Price">
<input type="submit" value="Add">
</form>
"""
        if err:
            body += "<p class='small'>Bad item or price.</p>"
        body += f"""
<div class="total">
<strong>Total: {h(money(total["grand"]))}</strong><br>
<span class="small">Today: {h(money(total["today"]))} | Items: {h(total["count"])}</span>
</div>
"""
        if not rows:
            body += "<p class='small'>No entries yet</p>"
        else:
            body += "<table><tr><th>Date</th><th>Item</th><th class='price'>Price</th><th></th></tr>"
            for row in rows:
                body += (
                    f"<tr><td>{h(date_short(row['created']))}</td>"
                    f"<td>{h(row['item'])}</td>"
                    f"<td class='price'>{h(money(row['price_cents']))}</td>"
                    f"<td class='del'><a href='{base}/{row['id']}/delete'>x</a></td></tr>"
                )
            body += "</table>"
        return phone_page("Finance", body, nav=[("Apps", "/")], extra_css=FINANCE_CSS)

    @flask_app.route(base + "/add", methods=["POST"])
    def finance_add():
        item = request.form.get("item", "").strip()
        try:
            price_cents = parse_price(request.form.get("price", ""))
        except ValueError:
            return redirect(f"{base}?err=1")
        if not item:
            return redirect(f"{base}?err=1")
        add_entry(item[:80], price_cents)
        return redirect(base)

    @flask_app.route(base + "/<int:entry_id>/delete", methods=["GET", "POST"])
    def finance_delete(entry_id):
        row = get_entry(entry_id)
        if not row:
            return redirect(base)
        if request.method == "POST":
            delete_entry(entry_id)
            return redirect(base)
        body = f"""
<p>Delete entry?</p>
<p><strong>{h(row['item'])}</strong><br>{h(money(row['price_cents']))}</p>
<form method="post" action="{base}/{entry_id}/delete">
<input class="danger" type="submit" value="Delete">
</form>
"""
        return phone_page("Delete", body, nav=[("Apps", "/"), ("Finance", base)], extra_css=FINANCE_CSS)
