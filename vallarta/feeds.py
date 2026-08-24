#!/usr/bin/env python3
"""Fetch the four Puerto Vallarta news feeds and their article pages.

Read-only. Standard library only. Enforces the source-access rules from
vallarta_agent_prompt.md:

  * each feed is read at most twice per day,
  * an article page is fetched at most once, ever,
  * at least 5 seconds pass between page requests.

The fetch ledger (cache/ledger.json) is what makes "never re-fetch" true across
runs, so it must never be deleted casually.
"""

import argparse
import gzip
import html
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "cache")
PAGES = os.path.join(CACHE, "pages")
RAW = os.path.join(CACHE, "pages-raw")
LEDGER = os.path.join(CACHE, "ledger.json")

UA = "Mozilla/5.0 (compatible; VallartaInfraMapper/1.0; +read-only research bot)"
MIN_GAP = 5.0          # seconds between requests
FEED_READS_PER_DAY = 2

SOURCES = os.path.join(ROOT, "state", "sources.json")


def load_city(city):
    """Feed registry for one city. Falls back to the Vallarta set if absent."""
    fallback = {"label": "Puerto Vallarta", "local_terms": [], "feeds": {
        "tribuna": {"name": "Tribuna de la Bahía", "url": "https://tribunadelabahia.com.mx/feed/"},
        "independiente": {"name": "Vallarta Independiente", "url": "https://vallartaindependiente.com/feed/"},
        "diario": {"name": "Diario de Vallarta", "url": "https://diariodevallarta.com/feed/"},
        "noticiaspv": {"name": "NoticiasPV", "url": "https://www.noticiaspv.com.mx/feed/"}}}
    if not os.path.exists(SOURCES):
        return fallback
    with open(SOURCES, encoding="utf-8") as fh:
        return json.load(fh)["cities"].get(city, fallback)


CITY = load_city(os.environ.get("MAPPER_CITY", "vallarta"))
FEEDS = {k: v["url"] for k, v in CITY["feeds"].items()}
OUTLET_NAMES = {k: v["name"] for k, v in CITY["feeds"].items()}


_last_request = [0.0]


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_ledger():
    if os.path.exists(LEDGER):
        with open(LEDGER, encoding="utf-8") as fh:
            return json.load(fh)
    return {"feed_reads": {}, "articles": {}}


def save_ledger(ledger):
    os.makedirs(CACHE, exist_ok=True)
    tmp = LEDGER + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, indent=2, ensure_ascii=False, sort_keys=True)
    os.replace(tmp, LEDGER)


def _throttle():
    gap = time.time() - _last_request[0]
    if gap < MIN_GAP:
        time.sleep(MIN_GAP - gap)
    _last_request[0] = time.time()


def get(url, timeout=45):
    """One polite HTTP GET. Returns decoded text."""
    _throttle()
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.6",
        "Accept-Encoding": "gzip",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        charset = resp.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


# ---------------------------------------------------------------- feed parsing

def _tag(block, name):
    m = re.search(r"<%s[^>]*>(.*?)</%s>" % (name, name), block, re.S | re.I)
    if not m:
        return None
    text = m.group(1)
    cd = re.match(r"\s*<!\[CDATA\[(.*?)\]\]>\s*$", text, re.S)
    if cd:
        text = cd.group(1)
    return html.unescape(text).strip()


def strip_html(fragment):
    if not fragment:
        return ""
    fragment = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", fragment)
    fragment = re.sub(r"(?i)</(p|div|h[1-6]|li|br)\s*>", "\n", fragment)
    fragment = re.sub(r"(?i)<br\s*/?>", "\n", fragment)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = html.unescape(fragment)
    fragment = re.sub(r"[ \t\xa0]+", " ", fragment)
    fragment = re.sub(r"\n\s*\n\s*", "\n\n", fragment)
    return fragment.strip()


def parse_feed(xml, outlet_key):
    items = []
    for block in re.findall(r"<item[^>]*>(.*?)</item>", xml, re.S | re.I):
        link = _tag(block, "link") or ""
        body = _tag(block, "content:encoded") or _tag(block, "description") or ""
        items.append({
            "outlet_key": outlet_key,
            "source_outlet": OUTLET_NAMES[outlet_key],
            "title": _tag(block, "title") or "",
            "article_url": link.strip(),
            "pub_date": _tag(block, "pubDate") or "",
            "author": _tag(block, "dc:creator"),
            "categories": [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                           for c in re.findall(r"<category[^>]*>(.*?)</category>", block, re.S | re.I)],
            "feed_text": strip_html(body),
        })
    return items


def read_feeds(ledger, force=False):
    """Read each feed, honouring the twice-per-day cap."""
    day = today()
    reads = ledger.setdefault("feed_reads", {}).setdefault(day, {})
    items, notes = [], []
    for key, url in FEEDS.items():
        count = reads.get(key, 0)
        if count >= FEED_READS_PER_DAY and not force:
            notes.append("%s: feed already read %d times today, skipped" % (key, count))
            cached = os.path.join(CACHE, "feed-%s-%s.xml" % (key, day))
            if os.path.exists(cached):
                with open(cached, encoding="utf-8") as fh:
                    items.extend(parse_feed(fh.read(), key))
            continue
        try:
            xml = get(url)
        except Exception as exc:                     # noqa: BLE001 - reported, not raised
            notes.append("%s: feed fetch failed (%s)" % (key, exc))
            continue
        reads[key] = count + 1
        with open(os.path.join(CACHE, "feed-%s-%s.xml" % (key, day)), "w", encoding="utf-8") as fh:
            fh.write(xml)
        got = parse_feed(xml, key)
        notes.append("%s: %d items" % (key, len(got)))
        items.extend(got)
    return items, notes


# ------------------------------------------------------------- article fetching

def page_path(url):
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", url).strip("-")[-120:]
    return os.path.join(PAGES, slug + ".json")


def extract_article(page_html):
    """Pull the body text and byline out of an article page."""
    body = None
    for pat in (r'(?is)<div[^>]+class="[^"]*(?:entry-content|post-content|td-post-content|article-content)[^"]*"[^>]*>(.*?)</div>\s*(?:<footer|<div[^>]+class="[^"]*(?:post-footer|entry-footer|sharedaddy|related))',
                r"(?is)<article[^>]*>(.*?)</article>"):
        m = re.search(pat, page_html)
        if m:
            body = m.group(1)
            break
    text = strip_html(body) if body else strip_html(page_html)
    author = None
    m = re.search(r'(?is)<meta[^>]+name="author"[^>]+content="([^"]+)"', page_html)
    if m:
        author = html.unescape(m.group(1)).strip()
    if not author:
        m = re.search(r'(?is)class="[^"]*author[^"]*"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{3,60})<', page_html)
        if m:
            author = html.unescape(m.group(1)).strip()
    date = None
    m = re.search(r'(?is)<meta[^>]+property="article:published_time"[^>]+content="([^"]+)"', page_html)
    if m:
        date = m.group(1)[:10]
    return {"text": text, "author": author, "published": date}


def fetch_article(url, ledger):
    """Fetch one article page, at most once ever. Returns (record, status)."""
    seen = ledger.setdefault("articles", {})
    path = page_path(url)
    if url in seen:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh), "cached"
        return None, "already-fetched-no-cache"
    os.makedirs(PAGES, exist_ok=True)
    try:
        page = get(url)
    except Exception as exc:                          # noqa: BLE001
        seen[url] = {"fetched": today(), "ok": False, "error": str(exc)}
        return None, "error: %s" % exc
    # Keep the raw page. "Never re-fetch" means a parser bug would otherwise be
    # permanent: with the HTML on disk, extraction can be redone offline forever.
    os.makedirs(RAW, exist_ok=True)
    with open(os.path.join(RAW, os.path.basename(path)[:-5] + ".html"), "w",
              encoding="utf-8") as fh:
        fh.write(page)
    art = extract_article(page)
    art["article_url"] = url
    art["fetched"] = today()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(art, fh, indent=2, ensure_ascii=False)
    seen[url] = {"fetched": today(), "ok": True, "chars": len(art["text"])}
    return art, "fetched"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "worklist-%s.json" % today()))
    ap.add_argument("--force-feeds", action="store_true",
                    help="ignore the twice-a-day feed cap (use only to recover from a failed run)")
    args = ap.parse_args()

    os.makedirs(CACHE, exist_ok=True)
    ledger = load_ledger()
    items, notes = read_feeds(ledger, force=args.force_feeds)
    save_ledger(ledger)

    for note in notes:
        print(note, file=sys.stderr)
    seen_urls, unique = set(), []
    for it in items:
        if it["article_url"] and it["article_url"] not in seen_urls:
            seen_urls.add(it["article_url"])
            unique.append(it)

    out = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "feed_notes": notes, "items": unique}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    print("%d unique feed items -> %s" % (len(unique), args.out), file=sys.stderr)


if __name__ == "__main__":
    main()
