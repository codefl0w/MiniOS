import os
import re
import time
import urllib.parse
from html import unescape
from html.parser import HTMLParser

import lxml.html
import requests
from env_loader import load_env
from flask import redirect, request

load_env()

from settings import app_settings, default_app_setting
from ui import h, phone_page

from reader import fetch_article, format_article_html

BASE_URL = "https://html.duckduckgo.com/html/"
USER_AGENT = os.environ.get("DUCKDUCKGO_USER_AGENT") or os.environ.get("SEARCH_USER_AGENT") or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
DUCKDUCKGO_CACHE_TTL = int((os.environ.get("DUCKDUCKGO_CACHE_TTL") or os.environ.get("SEARCH_CACHE_TTL") or "").strip() or "600")

REGIONS = [
    ("", "All Regions"),
    ("ar-es", "Argentina"),
    ("au-en", "Australia"),
    ("at-de", "Austria"),
    ("be-fr", "Belgium (fr)"),
    ("be-nl", "Belgium (nl)"),
    ("br-pt", "Brazil"),
    ("bg-bg", "Bulgaria"),
    ("ca-en", "Canada (en)"),
    ("ca-fr", "Canada (fr)"),
    ("ct-ca", "Catalonia"),
    ("cl-es", "Chile"),
    ("cn-zh", "China"),
    ("co-es", "Colombia"),
    ("hr-hr", "Croatia"),
    ("cz-cs", "Czech Republic"),
    ("dk-da", "Denmark"),
    ("ee-et", "Estonia"),
    ("fi-fi", "Finland"),
    ("fr-fr", "France"),
    ("de-de", "Germany"),
    ("gr-el", "Greece"),
    ("hk-tzh", "Hong Kong"),
    ("hu-hu", "Hungary"),
    ("is-is", "Iceland"),
    ("in-en", "India (en)"),
    ("id-en", "Indonesia (en)"),
    ("ie-en", "Ireland"),
    ("il-en", "Israel (en)"),
    ("it-it", "Italy"),
    ("jp-jp", "Japan"),
    ("kr-kr", "Korea"),
    ("lv-lv", "Latvia"),
    ("lt-lt", "Lithuania"),
    ("my-en", "Malaysia (en)"),
    ("mx-es", "Mexico"),
    ("nl-nl", "Netherlands"),
    ("nz-en", "New Zealand"),
    ("no-no", "Norway"),
    ("pk-en", "Pakistan (en)"),
    ("pe-es", "Peru"),
    ("ph-en", "Philippines (en)"),
    ("pl-pl", "Poland"),
    ("pt-pt", "Portugal"),
    ("ro-ro", "Romania"),
    ("ru-ru", "Russia"),
    ("xa-ar", "Saudi Arabia"),
    ("sg-en", "Singapore"),
    ("sk-sk", "Slovakia"),
    ("sl-sl", "Slovenia"),
    ("za-en", "South Africa"),
    ("es-ca", "Spain (ca)"),
    ("es-es", "Spain (es)"),
    ("se-sv", "Sweden"),
    ("ch-de", "Switzerland (de)"),
    ("ch-fr", "Switzerland (fr)"),
    ("tw-tzh", "Taiwan"),
    ("th-en", "Thailand (en)"),
    ("tr-tr", "Turkey"),
    ("us-en", "US (English)"),
    ("us-es", "US (Spanish)"),
    ("ua-uk", "Ukraine"),
    ("uk-en", "United Kingdom"),
    ("vn-en", "Vietnam (en)"),
]

DATE_FILTERS = [
    ("", "Any Time"),
    ("d", "Past Day"),
    ("w", "Past Week"),
    ("m", "Past Month"),
    ("y", "Past Year"),
]

_duckduckgo_cache = {}



def unpack_ddg_url(raw_url):
    if not raw_url:
        return ""
    if raw_url.startswith("//"):
        raw_url = "https:" + raw_url
    try:
        parsed = urllib.parse.urlparse(raw_url)
        qs = urllib.parse.parse_qs(parsed.query)
        if "uddg" in qs:
            return qs["uddg"][0]
    except Exception:
        pass
    return raw_url


def duckduckgo_config():
    try:
        cfg = app_settings("duckduckgo")
        if cfg:
            return cfg
    except Exception:
        pass
    try:
        cfg = app_settings("search")
        if cfg:
            return cfg
    except Exception:
        pass
    return {
        "cache_ttl": DUCKDUCKGO_CACHE_TTL,
        "reader_mode": True,
        "default_region": "",
        "default_time": "",
    }


def extract_spelling(tree, kl, df, base="/duckduckgo"):
    dym_nodes = tree.cssselect("#did_you_mean, .msg--spelling")
    if not dym_nodes:
        return ""
    target_node = dym_nodes[0]
    for a in target_node.cssselect("a"):
        href = a.get("href", "")
        parsed = urllib.parse.urlparse(href)
        qs = urllib.parse.parse_qs(parsed.query)
        target_q = qs.get("q", [""])[0]
        if target_q:
            params = {"q": target_q}
            if kl:
                params["kl"] = kl
            if df:
                params["df"] = df
            if "norw" in qs:
                params["norw"] = qs["norw"][0]
            a.set("href", f"{base}?{urllib.parse.urlencode(params)}")
    return lxml.html.tostring(target_node, encoding="unicode").strip()


def search_duckduckgo(query, kl="", df="", payload_override=None, is_more=False):
    cache_key = (query.strip().lower(), str(kl or ""), str(df or ""))
    now = time.time()
    ttl = duckduckgo_config().get("cache_ttl", DUCKDUCKGO_CACHE_TTL)
    cached = _duckduckgo_cache.get(cache_key)

    if not is_more and cached and now - cached["ts"] < ttl:
        return cached

    payload = {
        "q": query,
        "kl": kl or "",
        "df": df or "",
    }
    if payload_override:
        payload.update(payload_override)

    try:
        resp = requests.post(
            BASE_URL,
            data=payload,
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()

        tree = lxml.html.fromstring(resp.text)
        new_items = []

        result_nodes = tree.cssselect(".result")
        for node in result_nodes:
            title_nodes = node.cssselect(".result__title, .result__a")
            if not title_nodes:
                continue
            a_elem = node.cssselect(".result__a")
            raw_href = a_elem[0].get("href", "") if a_elem else ""
            clean_url = unpack_ddg_url(raw_href)

            title = title_nodes[0].text_content().strip()
            snippet_nodes = node.cssselect(".result__snippet")
            snippet = snippet_nodes[0].text_content().strip() if snippet_nodes else ""
            url_nodes = node.cssselect(".result__url")
            display_url = url_nodes[0].text_content().strip() if url_nodes else clean_url

            if title and clean_url:
                new_items.append({
                    "title": title,
                    "url": clean_url,
                    "display_url": display_url,
                    "snippet": snippet,
                })

        next_page = None
        nav_forms = tree.cssselect("div.nav-link form, form.nav-link")
        if nav_forms:
            form = nav_forms[0]
            inputs = {i.get("name"): i.get("value", "") for i in form.cssselect("input") if i.get("name") and i.get("name") != "b"}
            if inputs.get("s"):
                next_page = inputs

        spelling_html = extract_spelling(tree, kl, df)

        if is_more and cached:
            existing_items = cached.get("items", [])
            seen_urls = {item["url"] for item in existing_items}
            combined_items = list(existing_items)
            for item in new_items:
                if item["url"] not in seen_urls:
                    combined_items.append(item)
                    seen_urls.add(item["url"])
            items = combined_items
            if not spelling_html:
                spelling_html = cached.get("spelling", "")
        else:
            items = new_items

        result = {
            "query": query,
            "kl": kl,
            "df": df,
            "items": items,
            "next_page": next_page,
            "spelling": spelling_html,
            "ts": now,
            "error": "",
        }
        _duckduckgo_cache[cache_key] = result
        if len(_duckduckgo_cache) > 100:
            oldest = min(_duckduckgo_cache, key=lambda k: _duckduckgo_cache[k]["ts"])
            del _duckduckgo_cache[oldest]
        return result

    except requests.Timeout:
        if is_more and cached:
            cached["error"] = "Show more request timed out."
            return cached
        return {"query": query, "kl": kl, "df": df, "items": [], "next_page": None, "spelling": "", "ts": now, "error": "DuckDuckGo search timed out."}
    except Exception as exc:
        if is_more and cached:
            cached["error"] = str(exc)
            return cached
        return {"query": query, "kl": kl, "df": df, "items": [], "next_page": None, "spelling": "", "ts": now, "error": str(exc)}


fetch_readable_article = fetch_article


DUCKDUCKGO_CSS = """
.search-form{background:#0f1620;border:1px solid #263241;padding:6px;margin:0 0 8px;}
.search-row{display:block;}
.search-row input[type=text]{width:72%;box-sizing:border-box;background:#fff;color:#000;border:0;padding:6px;font-size:13px;}
.search-row input[type=submit]{width:26%;box-sizing:border-box;background:#95e1ff;color:#000;border:0;padding:6px;font-size:13px;font-weight:bold;}
.filter-row{margin-top:5px;}
.filter-row select{background:#191f2e;color:#fff;border:1px solid #263241;padding:3px;font-size:11px;max-width:48%;box-sizing:border-box;}
.spelling-box{background:#132032;border:1px solid #2d4f7c;padding:6px 8px;margin:6px 0;font-size:12px;color:#c2d6eb;line-height:1.3;}
.spelling-box a{color:#9fdfff;text-decoration:underline;}
.item{display:block;border-top:1px solid #263241;padding:7px 0;}
.title{font-size:13px;line-height:1.2;}
.snippet{color:#ffffff;font-size:11px;line-height:1.25;margin:3px 0;}
.meta{font-size:10px;color:#91a0af;}
.meta a{color:#ffd35a;}
.nav-box{border-top:1px solid #263241;padding:10px 0;text-align:center;}
.nav-box a{background:#0f1620;border:1px solid #263241;padding:6px 14px;color:#9fdfff;font-size:13px;font-weight:bold;display:inline-block;border-radius:3px;}
.err{color:#ff8b8b;font-size:12px;margin:6px 0;}
.article-title{font-size:14px;font-weight:bold;margin:0 0 8px;color:#9fdfff;}
.article-body{font-size:12px;line-height:1.35;white-space:pre-wrap;color:#fff;}
.orig{font-size:11px;color:#91a0af;margin:8px 0;}
"""


def build_filter_options(selected_kl, selected_df):
    kl_html = "".join(
        f"<option value='{h(code)}'{' selected' if code == selected_kl else ''}>{h(label)}</option>"
        for code, label in REGIONS
    )
    df_html = "".join(
        f"<option value='{h(code)}'{' selected' if code == selected_df else ''}>{h(label)}</option>"
        for code, label in DATE_FILTERS
    )
    return kl_html, df_html


def register_duckduckgo_routes(flask_app, prefix="/duckduckgo"):
    base = prefix.rstrip("/")

    @flask_app.route(base, methods=["GET"])
    def duckduckgo_index():
        cfg = duckduckgo_config()
        query = request.args.get("q", "").strip()
        kl = request.args.get("kl")
        if kl is None:
            kl = cfg.get("default_region", "")
        df = request.args.get("df")
        if df is None:
            df = cfg.get("default_time", "")

        is_more = request.args.get("more") == "1"
        reader_enabled = cfg.get("reader_mode", True)

        kl_opts, df_opts = build_filter_options(kl, df)

        form_html = f"""
        <form class='search-form' method='GET' action='{h(base)}'>
            <div class='search-row'>
                <input type='text' name='q' value='{h(query)}' placeholder='Search web...'>
                <input type='submit' value='Go'>
            </div>
            <div class='filter-row'>
                <select name='kl'>{kl_opts}</select>
                <select name='df'>{df_opts}</select>
            </div>
        </form>
        """

        if not query:
            body = form_html + "<div class='muted'>Enter query to search web.</div>"
            return phone_page("DuckDuckGo", body, nav=[("Apps", "/")], extra_css=DUCKDUCKGO_CSS)

        payload_override = None
        if is_more:
            payload_override = {}
            for key in ("s", "dc", "vqd", "api", "v", "o", "nextParams"):
                val = request.args.get(key)
                if val is not None:
                    payload_override[key] = val

        data = search_duckduckgo(query, kl=kl, df=df, payload_override=payload_override, is_more=is_more)
        body = form_html

        if data.get("error"):
            body += f"<div class='err'>{h(data['error'])}</div>"

        spelling_html = data.get("spelling")
        if spelling_html:
            body += f"<div class='spelling-box'>{spelling_html}</div>"

        items = data.get("items", [])
        if not items and not data.get("error"):
            body += "<div class='muted'>No results found.</div>"

        for item in items:
            title = h(item["title"])
            url = h(item["url"])
            display_url = h(item["display_url"])
            snippet = h(item["snippet"])

            reader_link = ""
            if reader_enabled:
                reader_params = {
                    "url": item["url"],
                    "q": query,
                }
                if kl:
                    reader_params["kl"] = kl
                if df:
                    reader_params["df"] = df
                reader_url = f"{base}/read?{urllib.parse.urlencode(reader_params)}"
                reader_link = f" | <a href='{h(reader_url)}'>[Reader]</a>"

            body += f"""
            <div class='item'>
                <div class='title'><a href='{url}'>{title}</a></div>
                <div class='snippet'>{snippet}</div>
                <div class='meta'>{display_url}{reader_link}</div>
            </div>
            """

        next_page = data.get("next_page")
        if next_page:
            more_params = dict(next_page)
            more_params["q"] = query
            more_params["more"] = "1"
            if kl:
                more_params["kl"] = kl
            if df:
                more_params["df"] = df
            more_url = f"{base}?{urllib.parse.urlencode(more_params)}"
            body += f"<div class='nav-box'><a href='{h(more_url)}'>Show more</a></div>"

        return phone_page(f"DuckDuckGo: {query}", body, nav=[("Apps", "/"), ("New Search", base)], extra_css=DUCKDUCKGO_CSS)

    @flask_app.route(base + "/read", methods=["GET"])
    def duckduckgo_read():
        url = request.args.get("url", "").strip()
        back_q = request.args.get("q", "").strip()
        kl = request.args.get("kl", "")
        df = request.args.get("df", "")

        nav_links = [("Apps", "/")]
        if back_q:
            back_params = {"q": back_q}
            if kl:
                back_params["kl"] = kl
            if df:
                back_params["df"] = df
            nav_links.append(("Back to DuckDuckGo", f"{base}?{urllib.parse.urlencode(back_params)}"))
        else:
            nav_links.append(("DuckDuckGo", base))

        if not url:
            return redirect(base)

        article = fetch_article(url)

        if article.get("error"):
            body = f"<div class='err'>{h(article['error'])}</div>"
            body += f"<div class='orig'><a href='{h(url)}' target='_blank'>Open original link</a></div>"
            return phone_page("Reader", body, nav=nav_links, extra_css=DUCKDUCKGO_CSS)

        title = h(article.get("title") or "Article")
        body_text = format_article_html(article.get("text", ""))

        body = f"""
        <div class='article-title'>{title}</div>
        <div class='orig'><a href='{h(url)}' target='_blank'>[Open Original Website]</a></div>
        <div class='article-body'>{body_text}</div>
        """
        return phone_page(title, body, nav=nav_links, extra_css=DUCKDUCKGO_CSS)

    # Legacy redirect
    @flask_app.route("/search")
    def search_redirect():
        args = dict(request.args)
        return redirect(f"{base}?{urllib.parse.urlencode(args)}" if args else base)
