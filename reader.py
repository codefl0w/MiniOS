import os
import re
import time
from html import unescape
from html.parser import HTMLParser

import requests
from ui import h

try:
    from readability import Document as ReadabilityDocument
    READABILITY_AVAILABLE = True
except ImportError:
    READABILITY_AVAILABLE = False

USER_AGENT = os.environ.get(
    "READER_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
)
ARTICLE_CACHE_TTL = int((os.environ.get("READER_CACHE_TTL") or "").strip() or "1800")
ARTICLE_MAX_LENGTH = 15000
ARTICLE_MAX_CACHE = 50

_article_cache = {}


class ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip = True
        elif tag in ("br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = False
        elif tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip and data:
            self.parts.append(data)

    def text(self):
        text = "".join(self.parts)
        text = unescape(text)
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
        return text.strip()


def article_to_text(html):
    parser = ArticleParser()
    parser.feed(html or "")
    return parser.text()


def fetch_via_jina(url):
    try:
        resp = requests.get(f"https://r.jina.ai/{url}", headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        if resp.status_code == 200 and resp.text:
            text = resp.text
            title = ""
            title_match = re.search(r"^Title:\s*(.+)$", text, re.MULTILINE)
            if title_match:
                title = title_match.group(1).strip()
            body = text.split("Markdown Content:", 1)[1].strip() if "Markdown Content:" in text else text
            if len(body) > ARTICLE_MAX_LENGTH:
                body = body[:ARTICLE_MAX_LENGTH] + "\n\n[article trimmed]"
            if len(body.strip()) > 50:
                return {"title": title, "text": body, "url": url, "ts": time.time(), "error": ""}
    except Exception as exc:
        return {"title": "", "text": "", "url": url, "ts": time.time(), "error": str(exc)}
    return {"title": "", "text": "", "url": url, "ts": time.time(), "error": "Reader extraction failed"}


def format_article_html(text):
    safe_text = h(text)
    converted = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', r'<a href="\2" target="_blank">\1</a>', safe_text)
    return converted.replace("\n", "<br>")


def fetch_article(url):
    if not url or "news.google.com" in url or "google.com" in url:
        return {"title": "", "text": "", "url": url, "ts": time.time(), "error": "Google News link could not be decoded"}

    now = time.time()
    cached = _article_cache.get(url)
    if cached and now - cached["ts"] < ARTICLE_CACHE_TTL:
        return cached

    last_err = ""
    if READABILITY_AVAILABLE:
        try:
            resp = requests.get(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                timeout=15,
            )
            resp.raise_for_status()
            doc = ReadabilityDocument(resp.text)
            text = article_to_text(doc.summary())
            if text and len(text.strip()) > 100:
                if len(text) > ARTICLE_MAX_LENGTH:
                    text = text[:ARTICLE_MAX_LENGTH] + "\n\n[article trimmed]"
                res = {"title": doc.title(), "text": text, "url": url, "ts": now, "error": ""}
                _article_cache[url] = res
                if len(_article_cache) > ARTICLE_MAX_CACHE:
                    del _article_cache[min(_article_cache, key=lambda k: _article_cache[k]["ts"])]
                return res
        except Exception as exc:
            last_err = str(exc)

    jina_res = fetch_via_jina(url)
    if jina_res and not jina_res.get("error") and len(jina_res.get("text", "").strip()) > 50:
        _article_cache[url] = jina_res
        if len(_article_cache) > ARTICLE_MAX_CACHE:
            del _article_cache[min(_article_cache, key=lambda k: _article_cache[k]["ts"])]
        return jina_res

    err_str = jina_res.get("error") or last_err or "Article fetch failed"
    return {"title": "", "text": "", "url": url, "ts": now, "error": err_str}
