import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import quote, urlencode, urlparse

import requests
from env_loader import load_env
from flask import redirect, request

load_env()

from reader import fetch_article, format_article_html
from settings import NEWS_LANGUAGES, NEWS_MODES, NEWS_TOPICS, app_settings, default_app_setting
from ui import h, phone_page

BASE_URL = "https://news.google.com/rss"
USER_AGENT = os.environ.get(
    "NEWS_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
)
NEWS_CACHE_TTL = int((os.environ.get("NEWS_CACHE_TTL") or "").strip() or "900")

_cache = {}
_session = None


def get_session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        })
        _session.cookies.set("CONSENT", "YES+cb.20210720-07-p0.en+FX+410", domain=".google.com")
        _session.cookies.set("SOCS", "CAESEwgDEgk2OTg2OTM0MjQaAmVuIAEaBgiA_L20Bg", domain=".google.com")
    return _session


class SummaryParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "p", "li"):
            self.parts.append("\n")

    def handle_data(self, data):
        if data:
            self.parts.append(data)

    def text(self):
        text = "".join(self.parts)
        text = unescape(text)
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n", text)
        return text.strip()



def summary_text(html):
    parser = SummaryParser()
    parser.feed(html or "")
    text = parser.text()
    if len(text) > 900:
        text = text[:897] + "..."
    return text


def clean_title(title, source):
    if source and title.endswith(" - " + source):
        return title[: -(len(source) + 3)].strip()
    if " - " in title:
        return title.rsplit(" - ", 1)[0].strip()
    return title.strip()


def format_date(value):
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).astimezone().strftime("%d.%m %H:%M")
    except Exception:
        try:
            return datetime.fromisoformat(value).strftime("%d.%m %H:%M")
        except Exception:
            return value[:16]


def lang_params(lang):
    return NEWS_LANGUAGES.get(lang, NEWS_LANGUAGES[default_app_setting("news", "default_lang")])


def request_args_from_query():
    cfg = app_settings("news")
    mode = request.args.get("mode", cfg["default_mode"])
    topic = request.args.get("topic", cfg["default_topic"]).upper()
    geo = request.args.get("geo", cfg["default_geo"]).strip()
    query = request.args.get("q", cfg["default_query"]).strip()
    lang = request.args.get("lang", cfg["default_lang"])
    if mode not in NEWS_MODES:
        mode = cfg["default_mode"] if cfg["default_mode"] in NEWS_MODES else default_app_setting("news", "default_mode")
    if topic not in NEWS_TOPICS:
        topic = cfg["default_topic"] if cfg["default_topic"] in NEWS_TOPICS else default_app_setting("news", "default_topic")
    if lang not in NEWS_LANGUAGES:
        lang = cfg["default_lang"] if cfg["default_lang"] in NEWS_LANGUAGES else default_app_setting("news", "default_lang")
    return {"mode": mode, "topic": topic, "geo": geo, "q": query, "lang": lang}


def build_url(params):
    lang = lang_params(params["lang"])
    qs = urlencode({"hl": lang["hl"], "gl": lang["gl"], "ceid": lang["ceid"]})
    mode = params["mode"]
    if mode == "top":
        return f"{BASE_URL}?{qs}"
    if mode == "topic":
        return f"{BASE_URL}/headlines/section/topic/{quote(params['topic'])}?{qs}"
    if mode == "geo":
        return f"{BASE_URL}/headlines/section/geo/{quote(params['geo'])}?{qs}"
    search_qs = urlencode({"q": params["q"], "hl": lang["hl"], "gl": lang["gl"], "ceid": lang["ceid"]})
    return f"{BASE_URL}/search?{search_qs}"


def feed_link(base, params, **updates):
    merged = dict(params)
    merged.update(updates)
    return base + "?" + urlencode(merged)


def parse_feed(xml_text):
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("No RSS channel")
    items = []
    for item in channel.findall("item")[:30]:
        source = item.find("source")
        source_name = source.text if source is not None and source.text else ""
        title = item.findtext("title", default="Untitled")
        items.append(
            {
                "title": clean_title(title, source_name),
                "source": source_name,
                "source_url": source.get("url", "") if source is not None else "",
                "link": item.findtext("link", default=""),
                "date": format_date(item.findtext("pubDate", default="")),
                "summary": summary_text(item.findtext("description", default="")),
            }
        )
    return {
        "title": channel.findtext("title", default="Google News"),
        "date": format_date(channel.findtext("lastBuildDate", default="")),
        "items": items,
        "copyright": channel.findtext("copyright", default=""),
    }


def fetch_news(params, force=False):
    key = tuple(sorted(params.items()))
    now = time.time()
    cached = _cache.get(key)
    if cached and not force and now - cached["ts"] < NEWS_CACHE_TTL:
        return cached

    url = build_url(params)
    try:
        session = get_session()
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        data = parse_feed(resp.text)
        data.update({"url": url, "ts": now, "error": "", "params": params})
        _cache[key] = data
        return data
    except Exception as exc:
        if cached:
            cached = dict(cached)
            cached["error"] = str(exc)
            return cached
        return {"title": "Google News", "date": "", "items": [], "url": url, "ts": now, "error": str(exc), "params": params}


def cache_age(ts):
    if not ts:
        return "none"
    age = max(0, int(time.time() - ts))
    if age < 60:
        return f"{age}s"
    return f"{age // 60}m {age % 60}s"


def decode_gnews_token(source_url):
    try:
        base64_str = source_url.split("/")[-1].split("?")[0]
        session = get_session()
        sg, ts = None, None
        endpoints = [
            f"https://news.google.com/articles/{base64_str}?hl=en-US&gl=US&ceid=US:en",
            f"https://news.google.com/rss/articles/{base64_str}?hl=en-US&gl=US&ceid=US:en",
            f"https://news.google.com/articles/{base64_str}",
        ]
        for ep in endpoints:
            try:
                r = session.get(ep, timeout=8)
                if r.status_code == 200:
                    sg_match = re.search(r'data-n-a-sg="([^"]+)"', r.text)
                    ts_match = re.search(r'data-n-a-ts="([^"]+)"', r.text)
                    if sg_match and ts_match:
                        sg, ts = sg_match.group(1), ts_match.group(1)
                        break
            except Exception:
                continue

        if not (sg and ts):
            return None

        batch_url = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
        payload = [
            "Fbv4je",
            f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{base64_str}",{ts},"{sg}"]',
        ]
        resp = session.post(
            batch_url,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            data=f"f.req={quote(json.dumps([[payload]]))}",
            timeout=8,
        )
        if resp.status_code == 200:
            parts = resp.text.split("\n\n")
            if len(parts) > 1:
                parsed = json.loads(parts[1])[:-2]
                url = json.loads(parsed[0][2])[1]
                if url and "google.com" not in url:
                    return url
    except Exception:
        pass
    return None


def resolve_via_search(title, source_url=""):
    try:
        from duckduckgo import search_duckduckgo
        cleaned = re.sub(r'["\']', '', title).strip()
        domain = urlparse(source_url).netloc.replace("www.", "") if source_url else ""
        queries = [f"{cleaned} site:{domain}", cleaned] if domain else [cleaned]
        for q in queries:
            res = search_duckduckgo(q)
            for it in res.get("items", []):
                u = it.get("url", "")
                if u and "google.com" not in u and "duckduckgo.com" not in u:
                    if domain and domain in u:
                        return u
                    if not domain:
                        return u
            if res.get("items"):
                first = res["items"][0].get("url", "")
                if first and "google.com" not in first and "duckduckgo.com" not in first:
                    return first
    except Exception:
        pass
    return None


def resolve_news_url(url, title="", source_url=""):
    if not url or "news.google.com" not in url:
        return url

    decoded = decode_gnews_token(url)
    if decoded:
        return decoded

    if title:
        search_decoded = resolve_via_search(title, source_url)
        if search_decoded:
            return search_decoded

    try:
        session = get_session()
        resp = session.get(url, timeout=10, allow_redirects=True)
        if resp.url and "google.com" not in resp.url:
            return resp.url
    except Exception:
        pass

    return url



NEWS_CSS = """
.bar{border-top:1px solid #263241;padding:5px 0;color:#91a0af;font-size:11px;}
.row{display:block;border-top:1px solid #263241;padding:7px 0;color:#fff;}
.title{display:block;color:#fff;font-size:12px;line-height:1.15;}
.src{display:block;color:#ffd35a;font-size:11px;margin-top:2px;}
.small{display:block;color:#91a0af;font-size:11px;margin-top:2px;}
.err{color:#ff8b8b;font-size:12px;}
.body{background:#0f1620;border:1px solid #263241;padding:6px;margin:6px 0;}
form{margin:4px 0;}
input[type=text]{width:100%;box-sizing:border-box;background:#fff;color:#000;border:0;padding:6px;font-size:13px;margin:0 0 4px;}
input[type=submit]{background:#95e1ff;color:#000;border:0;padding:6px 8px;font-size:13px;}
"""


def render_controls(base, params):
    body = "<div class='bar'>"
    body += f"<a href='{feed_link(base, params, mode='top')}'>Top</a> "
    for topic in NEWS_TOPICS:
        body += f"<a href='{feed_link(base, params, mode='topic', topic=topic)}'>{h(topic[:4])}</a> "
    body += "</div>"
    body += "<div class='bar'>"
    for lang, data in NEWS_LANGUAGES.items():
        body += f"<a href='{feed_link(base, params, lang=lang)}'>{h(lang)}</a> "
    body += "</div>"
    body += f"""
<form method="get" action="{base}">
<input type="hidden" name="mode" value="search">
<input type="hidden" name="lang" value="{h(params["lang"])}">
<input type="text" name="q" value="{h(params["q"])}" placeholder="Search">
<input type="submit" value="Search">
</form>
<form method="get" action="{base}">
<input type="hidden" name="mode" value="geo">
<input type="hidden" name="lang" value="{h(params["lang"])}">
<input type="text" name="geo" value="{h(params["geo"])}" placeholder="Location">
<input type="submit" value="Geo">
</form>
"""
    return body


def register_news_routes(flask_app, prefix="/news"):
    base = prefix.rstrip("/")

    @flask_app.route(base)
    @flask_app.route(base + "/")
    def news_index():
        params = request_args_from_query()
        force = request.args.get("refresh") == "1"
        feed = fetch_news(params, force=force)
        body = render_controls(base, params)
        body += f"<div class='small'>Mode: {h(params['mode'])} | Lang: {h(params['lang'])} | Cache: {h(cache_age(feed['ts']))}</div>"
        body += f"<div class='small'><a href='{feed_link(base, params, refresh='1')}'>Refresh</a></div>"
        if feed["error"]:
            body += f"<div class='err'>{h(feed['error'])}</div>"
        if not feed["items"]:
            body += "<p class='small'>No news</p>"
        for index, item in enumerate(feed["items"][:20]):
            link = feed_link(f"{base}/read/{index}", params)
            body += f"<a class='row' href='{link}'>"
            body += f"<span class='title'>{h(item['title'])}</span>"
            meta = item["source"] or "Google News"
            if item["date"]:
                meta += " | " + item["date"]
            body += f"<span class='src'>{h(meta)}</span></a>"
        return phone_page("News", body, nav=[("Apps", "/")], extra_css=NEWS_CSS)

    @flask_app.route(base + "/item/<int:index>")
    def news_item(index):
        params = request_args_from_query()
        feed = fetch_news(params)
        if index < 0 or index >= len(feed["items"]):
            return redirect(base)
        item = feed["items"][index]
        back = feed_link(base, params)
        read_url = feed_link(f"{base}/read/{index}", params)
        body = f"""
<div class="small">{h(item["source"] or "Google News")} | {h(item["date"])}</div>
<h3>{h(item["title"])}</h3>
<div class="body">{h(item["summary"]).replace(chr(10), "<br>")}</div>
<p><a href="{h(read_url)}">Read full article</a></p>
<p><a href="{h(back)}">Back</a></p>
"""
        return phone_page("News", body, nav=[("Apps", "/"), ("News", base)], extra_css=NEWS_CSS)

    @flask_app.route(base + "/read/<int:index>")
    def news_read(index):
        params = request_args_from_query()
        feed = fetch_news(params)
        if index < 0 or index >= len(feed["items"]):
            return redirect(base)
        item = feed["items"][index]
        back = feed_link(base, params)

        article_url = resolve_news_url(item["link"], title=item.get("title", ""), source_url=item.get("source_url", ""))
        article = fetch_article(article_url)

        meta = h(item.get("source") or "Google News")
        if item.get("date"):
            meta += " | " + h(item["date"])
        title = h(item.get("title") or "Article")

        if not article.get("error") and article.get("text", "").strip() and "google.com" not in article_url:
            art_title = h(article.get("title") or item["title"])
            body_text = format_article_html(article["text"])
            body = f"""
<div class="small">{meta}</div>
<h3>{art_title}</h3>
<div class="body">{body_text}</div>
<div class="small"><a href="{h(article_url)}" target="_blank">[Source Website]</a></div>
"""
        else:
            summary = h(item.get("summary") or "").replace("\n", "<br>")
            err = article.get("error") or "External site unavailable"
            orig_link = h(article_url if "google.com" not in article_url else item["link"])
            body = f"""
<div class="small">{meta}</div>
<h3>{title}</h3>
"""
            if summary:
                body += f"""
<div class="body">{summary}</div>
<div class="small muted">Full article unavailable on host network ({h(err)}). Summary displayed above.</div>
"""
            else:
                body += f"<div class='err'>{h(err)}</div>"
            body += f"""
<p><a href="{orig_link}" target="_blank">Open original article &raquo;</a></p>
"""
        return phone_page("Reader", body, nav=[("Apps", "/"), ("News", base), ("Back", back)], extra_css=NEWS_CSS)
