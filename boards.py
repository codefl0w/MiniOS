import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests
from env_loader import load_env
from flask import redirect, request

load_env()

from settings import BOARD_SORTS, app_settings, default_app_setting
from ui import h, phone_page

CACHE_TTL = int(os.environ.get("BOARDS_CACHE_TTL", "600"))
USER_AGENT = os.environ.get("BOARDS_USER_AGENT", "MiniOS/0.1 personal feature-phone RSS reader")
BASE_URL = "https://www.reddit.com/r/{sub}/{sort}/.rss"
NS = {"a": "http://www.w3.org/2005/Atom", "m": "http://search.yahoo.com/mrss/"}

_cache = {}


def subreddits():
    values = app_settings("boards")["subreddits"]
    return [str(value).strip() for value in values if str(value).strip()]


def sub_lookup():
    return {sub.lower(): sub for sub in subreddits()}


def default_sort():
    sort = app_settings("boards")["default_sort"]
    return sort if sort in BOARD_SORTS else default_app_setting("boards", "default_sort")


class ContentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.images = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == "a" and data.get("href"):
            self.links.append(unescape(data["href"]))
        elif tag == "img" and data.get("src"):
            self.images.append(unescape(data["src"]))

    def handle_data(self, data):
        if data:
            self.text.append(data)


def parse_content(html):
    parser = ContentParser()
    parser.feed(html or "")
    text = " ".join(part.strip() for part in parser.text if part.strip())
    text = unescape(re.sub(r"\s+", " ", text)).strip()
    split = re.search(r"\s+submitted by\s+", text, flags=re.I)
    if split:
        text = text[:split.start()].strip()
    if text.lower().startswith("submitted by "):
        text = ""
    text = text.replace("[link]", "").replace("[comments]", "").strip()
    return text, parser.links, parser.images


def is_photo_url(url):
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if "v.redd.it" in host or path.endswith((".mp4", ".webm", ".m3u8", ".mov")):
        return False
    return path.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))


def is_video_url(url):
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    return "v.redd.it" in host or path.endswith((".mp4", ".webm", ".m3u8", ".mov"))


def short_date(value):
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d.%m %H:%M")
    except Exception:
        return value[:16]


def entry_link(entry):
    link = entry.find("a:link", NS)
    return link.get("href", "") if link is not None else ""


def entry_author(entry):
    name = entry.findtext("a:author/a:name", default="", namespaces=NS)
    if name:
        return name.replace("/u/", "").strip()
    return ""


def parse_entry(entry):
    content = entry.findtext("a:content", default="", namespaces=NS)
    text, links, images = parse_content(content)
    thumbs = [node.get("url") for node in entry.findall("m:thumbnail", NS) if node.get("url")]
    images.extend(thumbs)

    photo_links = [url for url in links + images if is_photo_url(url)]
    video_links = [url for url in links if is_video_url(url)]
    outbound = next((url for url in links if "reddit.com/r/" not in url), "")
    image_url = photo_links[0] if photo_links else ""
    thumb_url = images[0] if images else image_url

    return {
        "id": entry.findtext("a:id", default="", namespaces=NS),
        "title": entry.findtext("a:title", default="Untitled", namespaces=NS),
        "link": entry_link(entry),
        "author": entry_author(entry),
        "published": short_date(entry.findtext("a:published", default="", namespaces=NS)),
        "updated": short_date(entry.findtext("a:updated", default="", namespaces=NS)),
        "text": text,
        "image_url": image_url,
        "thumb_url": thumb_url,
        "outbound": outbound,
        "is_video": bool(video_links) and not image_url,
    }


def feed_url(sub, sort):
    return BASE_URL.format(sub=sub, sort=sort)


def fetch_feed(sub, sort="hot", force=False):
    sub = sub_lookup().get(sub.lower(), sub)
    sort = sort if sort in BOARD_SORTS else default_sort()
    key = (sub.lower(), sort)
    now = time.time()
    cached = _cache.get(key)
    if cached and not force and now - cached["ts"] < CACHE_TTL:
        return cached

    url = feed_url(sub, sort)
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    entries = [parse_entry(entry) for entry in root.findall("a:entry", NS)]
    data = {"sub": sub, "sort": sort, "entries": entries, "ts": now, "url": url, "error": ""}
    _cache[key] = data
    return data


def get_feed(sub, sort="hot", force=False):
    try:
        return fetch_feed(sub, sort=sort, force=force)
    except Exception as exc:
        key = (sub.lower(), sort if sort in BOARD_SORTS else default_sort())
        cached = _cache.get(key)
        if cached:
            cached = dict(cached)
            cached["error"] = str(exc)
            return cached
        return {"sub": sub, "sort": sort, "entries": [], "ts": 0, "url": "", "error": str(exc)}


def find_post(sub, post_id):
    for sort in BOARD_SORTS:
        feed = get_feed(sub, sort=sort)
        for item in feed["entries"]:
            if item["id"] == post_id:
                return feed, item
    feed = get_feed(sub, sort="hot", force=True)
    for item in feed["entries"]:
        if item["id"] == post_id:
            return feed, item
    return feed, None


BOARDS_CSS = """
.sub{display:block;border-top:1px solid #263241;padding:8px 0;color:#fff;}
.row{display:block;border-top:1px solid #263241;padding:6px 0;min-height:58px;color:#fff;overflow:hidden;}
.thumb{float:left;width:55px;height:55px;margin:0 6px 3px 0;border:0;object-fit:cover;}
.title{display:block;font-size:12px;line-height:1.15;color:#fff;}
.small{display:block;color:#91a0af;font-size:11px;margin-top:2px;}
.photo{max-width:100%;height:auto;display:block;margin:6px 0;border:0;}
.posttext{background:#0f1620;border:1px solid #263241;padding:6px;margin:6px 0;color:#fff;}
.err{color:#ff8b8b;font-size:11px;}
"""


def register_boards_routes(flask_app, prefix="/boards"):
    base = prefix.rstrip("/")

    @flask_app.route(base)
    @flask_app.route(base + "/")
    def boards_index():
        body = ""
        for sub in subreddits():
            body += f"<a class='sub' href='{base}/{h(sub)}'><strong>r/{h(sub)}</strong><span class='small'>RSS feed</span></a>"
        return phone_page("Boards", body, nav=[("Apps", "/")], extra_css=BOARDS_CSS)

    @flask_app.route(base + "/<sub>")
    def boards_sub(sub):
        canonical = sub_lookup().get(sub.lower())
        if not canonical:
            return redirect(base)
        sort = request.args.get("sort", default_sort())
        sort = sort if sort in BOARD_SORTS else default_sort()
        force = request.args.get("refresh") == "1"
        feed = get_feed(canonical, sort=sort, force=force)
        sort_links = " ".join(f"<a href='{base}/{h(canonical)}?sort={s}'>{s}</a>" for s in BOARD_SORTS)
        body = f"<div class='small'>{sort_links} | <a href='{base}/{h(canonical)}?sort={sort}&refresh=1'>refresh</a></div>"
        if feed.get("error"):
            body += f"<div class='err'>Fetch error: {h(feed['error'])}</div>"
        if not feed["entries"]:
            body += "<p class='small'>No posts</p>"
        for item in feed["entries"][:20]:
            kind = "video" if item["is_video"] else ("img" if item["image_url"] else ("text" if item["text"] else "link"))
            body += f"<a class='row' href='{base}/{h(canonical)}/{h(item['id'])}'>"
            if item["thumb_url"]:
                body += f"<img class='thumb' src='{h(item['thumb_url'])}' alt=''>"
            body += f"<span class='title'>{h(item['title'])}</span>"
            body += f"<span class='small'>{kind} | {h(item['published'])}"
            if item["author"]:
                body += f" | u/{h(item['author'])}"
            body += "</span></a>"
        return phone_page(f"r/{canonical}", body, nav=[("Apps", "/"), ("Boards", base)], extra_css=BOARDS_CSS)

    @flask_app.route(base + "/<sub>/<post_id>")
    def boards_post(sub, post_id):
        canonical = sub_lookup().get(sub.lower())
        if not canonical:
            return redirect(base)
        _feed, item = find_post(canonical, post_id)
        if not item:
            return phone_page("Missing", "<p class='small'>Post not found in cached feed.</p>", nav=[("Boards", base)]), 404

        body = f"<h3>{h(item['title'])}</h3>"
        meta = item["published"]
        if item["author"]:
            meta += f" | u/{item['author']}"
        body += f"<div class='small'>{h(meta)}</div>"
        if item["image_url"]:
            body += f"<img class='photo' src='{h(item['image_url'])}' alt=''>"
        elif item["thumb_url"]:
            body += f"<img class='photo' src='{h(item['thumb_url'])}' alt=''>"
            body += "<div class='small'>Preview only. Video/external media skipped.</div>"
        if item["text"]:
            body += f"<div class='posttext'>{h(item['text'])}</div>"
        if item["outbound"] and not item["image_url"]:
            body += f"<p><a href='{h(item['outbound'])}'>Open link</a></p>"
        if item["link"]:
            body += f"<p><a href='{h(item['link'])}'>Reddit comments</a></p>"
        return phone_page(f"r/{canonical}", body, nav=[("Apps", "/"), ("Back", f"{base}/{canonical}")], extra_css=BOARDS_CSS)
