import os
import json
import re
import time
from urllib.parse import urlencode, urlparse, parse_qs

import requests
from env_loader import load_env
from flask import redirect, request

load_env()

from settings import app_settings
from ui import h, phone_page

YOUTUBE_SEARCH_URL = "https://www.youtube.com/results"
MOBILE_WATCH_URL = "https://m.youtube.com/watch"
USER_AGENT = os.environ.get(
    "YOUTUBEWAP_USER_AGENT",
    "Mozilla/5.0",
)
DEFAULT_QUERY = "music"
DEFAULT_LIMIT = 12
DEFAULT_CACHE_TTL = int(os.environ.get("YOUTUBEWAP_CACHE_TTL", "900"))

_cache = {}


def youtubewap_config():
    cfg = app_settings("youtubewap")
    try:
        limit = int(cfg.get("limit", DEFAULT_LIMIT))
    except Exception:
        limit = DEFAULT_LIMIT
    try:
        cache_ttl = int(cfg.get("cache_ttl", DEFAULT_CACHE_TTL))
    except Exception:
        cache_ttl = DEFAULT_CACHE_TTL
    return {
        "default_query": str(cfg.get("default_query", DEFAULT_QUERY)).strip() or DEFAULT_QUERY,
        "limit": max(1, min(limit, 25)),
        "cache_ttl": max(0, cache_ttl),
    }


def video_id_from_text(value):
    value = (value or "").strip()
    if not value:
        return ""
    if re.fullmatch(r"[-_A-Za-z0-9]{11}", value):
        return value

    try:
        parsed = urlparse(value)
    except Exception:
        return ""

    host = parsed.netloc.lower()
    if "youtu.be" in host:
        candidate = parsed.path.strip("/").split("/")[0]
        return candidate if re.fullmatch(r"[-_A-Za-z0-9]{11}", candidate or "") else ""
    if "youtube.com" in host:
        qs_id = parse_qs(parsed.query).get("v", [""])[0]
        if re.fullmatch(r"[-_A-Za-z0-9]{11}", qs_id or ""):
            return qs_id
        parts = [part for part in parsed.path.split("/") if part]
        for marker in ("shorts", "embed", "live"):
            if marker in parts:
                index = parts.index(marker) + 1
                if index < len(parts) and re.fullmatch(r"[-_A-Za-z0-9]{11}", parts[index]):
                    return parts[index]
    return ""


def mobile_watch_link(video_id):
    return MOBILE_WATCH_URL + "?" + urlencode({"v": video_id})


def first_text(value):
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    if value.get("simpleText"):
        return value["simpleText"]
    runs = value.get("runs")
    if isinstance(runs, list):
        return "".join(str(run.get("text", "")) for run in runs if isinstance(run, dict)).strip()
    return ""


def first_thumbnail(value):
    thumbs = value.get("thumbnails") if isinstance(value, dict) else None
    if not isinstance(thumbs, list) or not thumbs:
        return ""
    preferred = thumbs[-1]
    return preferred.get("url", "") if isinstance(preferred, dict) else ""


def clean_thumb_url(url):
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    return url.replace("\\u0026", "&")


def short_text(value, limit=120):
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def extract_yt_initial_data(html):
    match = re.search(r"(?:var\s+)?ytInitialData\s*=", html)
    if not match:
        return None
    start = html.find("{", match.end())
    if start < 0:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(html[start:])
        return data
    except Exception:
        return None


def walk_video_renderers(value):
    if isinstance(value, dict):
        renderer = value.get("videoRenderer")
        if isinstance(renderer, dict):
            yield renderer
        for child in value.values():
            yield from walk_video_renderers(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_video_renderers(child)


def item_from_renderer(renderer):
    video_id = renderer.get("videoId", "")
    if not re.fullmatch(r"[-_A-Za-z0-9]{11}", video_id or ""):
        return None
    desc = ""
    snippets = renderer.get("detailedMetadataSnippets")
    if isinstance(snippets, list) and snippets:
        desc = first_text(snippets[0].get("snippetText", {}))
    item = {
        "id": video_id,
        "title": first_text(renderer.get("title", {})) or "Untitled video",
        "channel": first_text(renderer.get("ownerText", {})) or first_text(renderer.get("longBylineText", {})),
        "views": first_text(renderer.get("viewCountText", {})),
        "published": first_text(renderer.get("publishedTimeText", {})),
        "duration": first_text(renderer.get("lengthText", {})),
        "thumb": clean_thumb_url(first_thumbnail(renderer.get("thumbnail", {}))),
        "description": short_text(desc),
    }
    return item


def dedupe_results(results, limit):
    seen = set()
    unique = []
    for item in results:
        video_id = item["id"]
        if video_id in seen:
            continue
        seen.add(video_id)
        unique.append(item)
    return unique[:limit]


def extract_results(html, limit):
    data = extract_yt_initial_data(html)
    if data:
        items = []
        for renderer in walk_video_renderers(data):
            item = item_from_renderer(renderer)
            if item:
                items.append(item)
        parsed = dedupe_results(items, limit)
        if parsed:
            return parsed

    results = []
    for match in re.finditer(r'"videoId":"(?P<id>[-_A-Za-z0-9]{11})".{0,900}?"title":\{"runs":\[\{"text":"(?P<title>.*?)"\}', html):
        title = match.group("title")
        title = title.encode("utf-8").decode("unicode_escape", errors="ignore")
        title = re.sub(r"\\u0026", "&", title)
        title = re.sub(r"\s+", " ", title).strip()
        if title:
            video_id = match.group("id")
            results.append(
                {
                    "id": video_id,
                    "title": title,
                    "channel": "",
                    "views": "",
                    "published": "",
                    "duration": "",
                    "thumb": f"https://i.ytimg.com/vi/{video_id}/default.jpg",
                    "description": "",
                }
            )
    return dedupe_results(results, limit)


def search_youtube(query, force=False):
    query = (query or "").strip()
    if not query:
        return {"items": [], "error": "", "ts": 0}

    cfg = youtubewap_config()
    now = time.time()
    cached = _cache.get(query.lower())
    if cached and not force and now - cached["ts"] < cfg["cache_ttl"]:
        return cached

    url = YOUTUBE_SEARCH_URL + "?" + urlencode({"search_query": query})
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=12)
        resp.raise_for_status()
        data = {"items": extract_results(resp.text, cfg["limit"]), "error": "", "ts": now}
        _cache[query.lower()] = data
        return data
    except Exception as exc:
        if cached:
            cached = dict(cached)
            cached["error"] = str(exc)
            return cached
        return {"items": [], "error": str(exc), "ts": now}


def cache_age(ts):
    if not ts:
        return "none"
    age = max(0, int(time.time() - ts))
    if age < 60:
        return f"{age}s"
    return f"{age // 60}m"


def search_link(base, query, **updates):
    params = {"q": query}
    params.update(updates)
    return base + "?" + urlencode(params)


YOUTUBEWAP_CSS = """
.hero{background:#0f1620;border:1px solid #263241;padding:6px;margin:0 0 6px;}
.brand{color:#ff6b6b;font-weight:bold;}
.bar{border-top:1px solid #263241;padding:5px 0;color:#91a0af;font-size:11px;clear:both;}
.row{display:block;border-top:1px solid #263241;padding:7px 0;color:#fff;min-height:58px;overflow:hidden;}
.thumb{float:left;width:74px;height:56px;margin:0 7px 4px 0;background:#0b0f16;border:1px solid #263241;object-fit:cover;}
.title{display:block;color:#fff;font-size:12px;line-height:1.15;font-weight:bold;}
.meta{display:block;color:#ffd35a;font-size:11px;margin-top:2px;}
.small{display:block;color:#91a0af;font-size:11px;margin-top:2px;}
.pill{display:inline-block;background:#263241;color:#fff;padding:2px 4px;margin:2px 2px 0 0;font-size:10px;}
.err{color:#ff8b8b;font-size:12px;}
.clear{clear:both;height:0;overflow:hidden;}
.preview{background:#0f1620;border:1px solid #263241;padding:6px;margin:6px 0;}
.preview img{width:100%;max-width:320px;height:auto;border:0;display:block;margin:0 0 5px;}
form{margin:4px 0;}
input[type=text]{width:100%;box-sizing:border-box;background:#fff;color:#000;border:0;padding:6px;font-size:13px;margin:0 0 4px;}
input[type=submit]{background:#95e1ff;color:#000;border:0;padding:6px 8px;font-size:13px;}
"""


def render_home(base, query="", feed=None):
    feed = feed or {"items": [], "error": "", "ts": 0}
    body = f"""
<div class="hero"><span class="brand">YT WAP</span><span class="small">Fast video search for small browsers</span></div>
<form method="get" action="{base}">
<input type="text" name="q" value="{h(query)}" placeholder="Search YouTube">
<input type="submit" value="Search">
</form>
<form method="get" action="{base}/open">
<input type="text" name="v" value="" placeholder="Paste video URL or ID">
<input type="submit" value="Open">
</form>
<div class="bar"><a href="{h(MOBILE_WATCH_URL.replace('/watch', ''))}">Open m.youtube.com</a></div>
"""
    if query:
        body += f"<div class='small'>Search: {h(query)} | Cache: {h(cache_age(feed['ts']))} | <a href='{h(search_link(base, query, refresh='1'))}'>Refresh</a></div>"
    if feed["error"]:
        body += f"<div class='err'>{h(feed['error'])}</div>"
    if query and not feed["items"] and not feed["error"]:
        body += "<p class='small'>No videos found. Try opening mobile YouTube below.</p>"
    for item in feed["items"]:
        detail_url = f"{base}/video/{h(item['id'])}?" + urlencode({"q": query})
        meta_parts = [part for part in (item.get("channel"), item.get("views"), item.get("published")) if part]
        meta = " | ".join(meta_parts)
        thumb = item.get("thumb") or f"https://i.ytimg.com/vi/{item['id']}/default.jpg"
        body += f"<a class='row' href='{detail_url}'>"
        body += f"<img class='thumb' src='{h(thumb)}' alt=''>"
        body += f"<span class='title'>{h(item['title'])}</span>"
        if meta:
            body += f"<span class='meta'>{h(meta)}</span>"
        if item.get("duration"):
            body += f"<span class='pill'>{h(item['duration'])}</span>"
        if item.get("description"):
            body += f"<span class='small'>{h(item['description'])}</span>"
        body += "<span class='clear'></span></a>"
    if query:
        mobile_search = "https://m.youtube.com/results?" + urlencode({"search_query": query})
        body += f"<p class='small'><a href='{h(mobile_search)}'>Open this search on m.youtube.com</a></p>"
    return body


def render_video_page(base, video_id, query=""):
    watch_url = mobile_watch_link(video_id)
    thumb = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    back = search_link(base, query) if query else base
    body = f"""
<div class="preview">
<img src="{h(thumb)}" alt="">
<span class="small">Video ID: {h(video_id)}</span>
</div>
<p><a href="{h(watch_url)}">Play on m.youtube.com</a></p>
<p><a href="https://www.youtube.com/watch?v={h(video_id)}">Open full YouTube</a></p>
<p><a href="{h(back)}">Back</a></p>
"""
    return body


def register_youtubewap_routes(flask_app, prefix="/youtubewap"):
    base = prefix.rstrip("/")

    @flask_app.route(base)
    @flask_app.route(base + "/")
    def youtubewap_index():
        cfg = youtubewap_config()
        query = request.args.get("q", "").strip()
        if not query and request.args.get("default") == "1":
            query = cfg["default_query"]
        force = request.args.get("refresh") == "1"
        feed = search_youtube(query, force=force) if query else None
        body = render_home(base, query, feed)
        body += f"<p class='small'><a href='{h(base)}?default=1'>Default search: {h(cfg['default_query'])}</a></p>"
        return phone_page("YouTube WAP", body, nav=[("Apps", "/"), ("Settings", "/settings/youtubewap")], extra_css=YOUTUBEWAP_CSS)

    @flask_app.route(base + "/open")
    def youtubewap_open():
        video_id = video_id_from_text(request.args.get("v", ""))
        if not video_id:
            return redirect(base)
        return redirect(mobile_watch_link(video_id))

    @flask_app.route(base + "/video/<video_id>")
    def youtubewap_video(video_id):
        if not re.fullmatch(r"[-_A-Za-z0-9]{11}", video_id or ""):
            return redirect(base)
        query = request.args.get("q", "").strip()
        return phone_page("Video Preview", render_video_page(base, video_id, query), nav=[("Apps", "/"), ("YouTube", base)], extra_css=YOUTUBEWAP_CSS)
