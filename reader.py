import os
import re
import time

import lxml.html
import requests

try:
    from readability import Document as ReadabilityDocument
    READABILITY_AVAILABLE = True
except ImportError:
    READABILITY_AVAILABLE = False

USER_AGENT = os.environ.get(
    "READER_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
)
JINA_USER_AGENT = "Mozilla/5.0"
ARTICLE_CACHE_TTL = int((os.environ.get("READER_CACHE_TTL") or "").strip() or "1800")
ARTICLE_MAX_LENGTH = 15000
ARTICLE_MAX_CACHE = 50

_article_cache = {}


def is_html(content):
    if not content:
        return False
    lower = content[:500].lower()
    return "<html" in lower or "<body" in lower or "<div" in lower or "<p>" in lower or "<article" in lower


def sanitize_html(raw_html):
    if not raw_html:
        return ""
    try:
        tree = lxml.html.fromstring(raw_html)
        drop_tags = ["script", "style", "form", "iframe", "noscript", "svg", "button", "input", "select", "textarea"]
        for el in tree.xpath("//" + "|//".join(drop_tags)):
            el.drop_tree()

        drop_patterns = [
            "//*[contains(@class, 'ad-') or contains(@class, 'adsbygoogle') or contains(@class, 'sharing') or contains(@class, 'cookie') or contains(@class, 'banner') or contains(@class, 'sidebar') or contains(@class, 'modal') or contains(@class, 'popup')]",
            "//*[contains(@id, 'cookie') or contains(@id, 'sharing') or contains(@id, 'modal') or contains(@id, 'popup') or contains(@id, 'login')]",
        ]
        for pat in drop_patterns:
            try:
                for el in tree.xpath(pat):
                    el.drop_tree()
            except Exception:
                pass

        for img in tree.xpath("//img"):
            src = img.get("src", "")
            if not src or src.startswith("data:") or "spacer" in src or "1x1" in src:
                img.drop_tree()
                continue
            img.set("style", "max-width:100%;height:auto;display:block;margin:6px 0;")
            img.attrib.pop("srcset", None)
            img.attrib.pop("sizes", None)

        for a in tree.xpath("//a"):
            a.set("target", "_blank")
            if not a.text_content().strip() and not len(a):
                a.drop_tree()

        body = tree.body if hasattr(tree, "body") and tree.body is not None else tree
        return lxml.html.tostring(body, encoding="unicode").strip()
    except Exception:
        return raw_html


def clean_markdown_article(md_text):
    if not md_text:
        return ""

    h1_match = re.search(r"^(#\s+[^\n]+)", md_text, re.MULTILINE)
    if h1_match:
        md_text = md_text[h1_match.start():]

    cutoff_patterns = [
        r"\n#{1,4}\s*(Comments|Responses|Discussion)\b",
        r"\n\*\s*TAGS\b",
        r"\n#{1,4}\s*\[?RELATED ARTICLES\b",
        r"\n#{1,4}\s*\[?MORE FROM AUTHOR\b",
        r"\nWe use cookies on our website",
        r"\nPrivacy Overview\b",
        r"\n©\s*\d{4}\s+.*All rights reserved",
    ]
    for pat in cutoff_patterns:
        m = re.search(pat, md_text, re.IGNORECASE)
        if m:
            md_text = md_text[:m.start()]

    lines = md_text.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^\[\s*\]\([^\)]+\)$", stripped):
            continue
        if re.match(r"^\[(Facebook|Twitter|ReddIt|Copy URL|Telegram|Instagram|Pinterest|LinkedIn|Share)\]\(", stripped, re.IGNORECASE):
            continue
        if stripped.lower() in ("advertisement", "discover more", "sponsored", "add gizmochina as preferred source on google"):
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def parse_inline_markdown(text):
    text = re.sub(
        r'!\[([^\]]*)\]\((https?://[^\)\s]+)[^\)]*\)',
        r'<img src="\2" alt="\1" style="max-width:100%;height:auto;display:block;margin:6px 0;">',
        text,
    )
    text = re.sub(
        r'\[([^\]]+)\]\((https?://[^\)\s]+)[^\)]*\)',
        r'<a href="\2" target="_blank">\1</a>',
        text,
    )
    text = re.sub(r'(\*\*|__)(.*?)\1', r'<b>\2</b>', text)
    text = re.sub(r'(\*|_)(.*?)\1', r'<i>\2</i>', text)
    return text


def markdown_to_html(md_text):
    if not md_text:
        return ""

    lines = md_text.split("\n")
    html_out = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_out.append("</ul>")
                in_list = False
            continue

        list_match = re.match(r"^[\*\-]\s+(.+)$", stripped)
        if list_match:
            if not in_list:
                html_out.append("<ul>")
                in_list = True
            content = parse_inline_markdown(list_match.group(1))
            html_out.append(f"<li>{content}</li>")
            continue
        elif in_list:
            html_out.append("</ul>")
            in_list = False

        h_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if h_match:
            level = min(len(h_match.group(1)) + 2, 6)
            content = parse_inline_markdown(h_match.group(2))
            html_out.append(f"<h{level}>{content}</h{level}>")
            continue

        if stripped.startswith(">"):
            content = parse_inline_markdown(stripped.lstrip("> ").strip())
            html_out.append(f"<blockquote>{content}</blockquote>")
            continue

        content = parse_inline_markdown(stripped)
        html_out.append(f"<p>{content}</p>")

    if in_list:
        html_out.append("</ul>")

    return "\n".join(html_out)


def format_article_html(content):
    if not content:
        return ""
    if is_html(content):
        return sanitize_html(content)
    cleaned = clean_markdown_article(content)
    return markdown_to_html(cleaned)


def fetch_via_jina(url):
    try:
        resp = requests.get(
            f"https://r.jina.ai/{url}",
            headers={"X-Return-Format": "html", "User-Agent": JINA_USER_AGENT},
            timeout=20,
        )
        if resp.status_code == 200 and resp.text:
            text = resp.text
            if is_html(text) and READABILITY_AVAILABLE and "just a moment" not in text.lower():
                try:
                    doc = ReadabilityDocument(text)
                    summary = doc.summary()
                    if summary and len(summary.strip()) > 100:
                        cleaned = sanitize_html(summary)
                        if len(cleaned) > ARTICLE_MAX_LENGTH:
                            cleaned = cleaned[:ARTICLE_MAX_LENGTH] + "\n\n<p><i>[article trimmed]</i></p>"
                        return {"title": doc.title(), "text": cleaned, "url": url, "ts": time.time(), "engine": "Jina / Readability-lxml", "error": ""}
                except Exception:
                    pass

        resp = requests.get(f"https://r.jina.ai/{url}", headers={"User-Agent": JINA_USER_AGENT}, timeout=20)
        if resp.status_code == 200 and resp.text:
            text = resp.text
            title = ""
            title_match = re.search(r"^Title:\s*(.+)$", text, re.MULTILINE)
            if title_match:
                title = title_match.group(1).strip()
            body = text.split("Markdown Content:", 1)[1].strip() if "Markdown Content:" in text else text
            formatted = format_article_html(body)
            if len(formatted.strip()) > 50:
                if len(formatted) > ARTICLE_MAX_LENGTH:
                    formatted = formatted[:ARTICLE_MAX_LENGTH] + "\n\n<p><i>[article trimmed]</i></p>"
                return {"title": title, "text": formatted, "url": url, "ts": time.time(), "engine": "Jina / MiniOS Reader", "error": ""}
    except Exception as exc:
        return {"title": "", "text": "", "url": url, "ts": time.time(), "engine": "", "error": str(exc)}
    return {"title": "", "text": "", "url": url, "ts": time.time(), "engine": "", "error": "Reader extraction failed"}


def fetch_article(url):
    if not url or "news.google.com" in url or "google.com" in url:
        return {"title": "", "text": "", "url": url, "ts": time.time(), "engine": "", "error": "Google News link could not be decoded"}

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
            cleaned = sanitize_html(doc.summary())
            if cleaned and len(cleaned.strip()) > 100:
                if len(cleaned) > ARTICLE_MAX_LENGTH:
                    cleaned = cleaned[:ARTICLE_MAX_LENGTH] + "\n\n<p><i>[article trimmed]</i></p>"
                res = {"title": doc.title(), "text": cleaned, "url": url, "ts": now, "engine": "Readability-lxml", "error": ""}
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
    return {"title": "", "text": "", "url": url, "ts": now, "engine": "", "error": err_str}
