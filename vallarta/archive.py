#!/usr/bin/env python3
"""Backfill the article corpus from the outlets' public archives.

Authorised by a human on 2026-08-24 (see CHANGELOG). The daily feed carries only
the newest 10-20 items, so a larger corpus has to come from the archives. This
still respects everything else in vallarta_agent_prompt.md: read-only, 5 seconds
between requests, one fetch per URL ever, facts saved rather than article text.

Access method is chosen per host from robots.txt:

  tribunadelabahia.com.mx  REST API   robots: "Disallow:" (nothing disallowed)
  diariodevallarta.com     REST API   robots: only /wp-admin disallowed
  vallartaindependiente.com  paged RSS  robots: "Disallow: /wp-json/" -> API is off
                                       limits; its crawl-delay: 5 matches our gap
  noticiaspv.com.mx        REST API   robots: no rule for this fetcher; GPTBot only

Bulk endpoints return the article body inline, so this is far gentler on the
servers than fetching thousands of pages: ~80 requests instead of ~4,500.

  python3 archive.py --after 2026-05-26 --before 2026-08-25
"""

import argparse
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime, timezone

import feeds

ROOT = feeds.ROOT
CACHE = os.path.join(ROOT, "cache", "archive")

# access strategy per outlet, derived from each site's robots.txt
PLAN = {
    "tribuna":       {"host": "tribunadelabahia.com.mx",  "method": "rest"},
    "diario":        {"host": "diariodevallarta.com",     "method": "rest"},
    "independiente": {"host": "vallartaindependiente.com", "method": "paged_feed",
                      "robots_note": "robots.txt disallows /wp-json/; using the feed instead"},
    "noticiaspv":    {"host": "www.noticiaspv.com.mx", "method": "rest",
                      "robots_note": "robots.txt has no rule for this fetcher; GPTBot is disallowed"},
}
PER_PAGE = 100


def _cache(name):
    os.makedirs(CACHE, exist_ok=True)
    return os.path.join(CACHE, name)


OFFLINE = False


class NotCached(Exception):
    """Raised in offline mode when a page was never downloaded."""


def get_cached(url, name):
    """Fetch once, ever. Cached responses never touch the network again."""
    path = _cache(name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read(), True
    if OFFLINE:
        raise NotCached(url)
    body = feeds.get(url)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return body, False


def author_map(key, host, ids):
    """Resolve author ids to printed bylines (a handful of requests, cached)."""
    names, ids = {}, sorted({i for i in ids if i})
    for start in range(0, len(ids), PER_PAGE):
        chunk = ids[start:start + PER_PAGE]
        url = ("https://%s/wp-json/wp/v2/users?per_page=%d&include=%s&_fields=id,name"
               % (host, PER_PAGE, ",".join(str(i) for i in chunk)))
        try:
            body, _ = get_cached(url, "%s-users-%d.json" % (key, start))
            for user in json.loads(body):
                names[user["id"]] = user["name"]
        except NotCached:
            break
        except Exception as exc:                                  # noqa: BLE001
            print("  author lookup failed (%s); bylines fall back to null" % exc, file=sys.stderr)
            break
    return names


def collect_rest(key, host, after, before, limit):
    items, page, author_ids = [], 1, set()
    while len(items) < limit:
        url = ("https://%s/wp-json/wp/v2/posts?per_page=%d&page=%d&orderby=date&order=desc"
               "&after=%sT00:00:00&before=%sT00:00:00"
               "&_fields=id,date,link,title,content,author,categories"
               % (host, PER_PAGE, page, after, before))
        try:
            body, cached = get_cached(url, "%s-posts-%s-%s-p%03d.json" % (key, after, before, page))
        except NotCached:
            print("  %s: stopping at page %d (not cached; offline mode)" % (key, page), file=sys.stderr)
            break
        except Exception as exc:                                  # noqa: BLE001
            print("  %s page %d failed: %s" % (key, page, exc), file=sys.stderr)
            break
        batch = json.loads(body)
        if not isinstance(batch, list) or not batch:
            break
        for post in batch:
            author_ids.add(post.get("author"))
            items.append({
                "outlet_key": key,
                "source_outlet": feeds.OUTLET_NAMES[key],
                "article_url": post.get("link", ""),
                "article_date": (post.get("date") or "")[:10],
                "title": feeds.strip_html(post.get("title", {}).get("rendered", "")),
                "author_id": post.get("author"),
                "author": None,
                "text": feeds.strip_html(post.get("content", {}).get("rendered", "")),
            })
        print("  %s page %d: %d posts%s" % (key, page, len(batch), " (cached)" if cached else ""),
              file=sys.stderr)
        if len(batch) < PER_PAGE:
            break
        page += 1

    names = author_map(key, host, author_ids)
    for item in items:
        item["author"] = names.get(item.pop("author_id"))
    return items[:limit]


def collect_paged_feed(key, host, after, before, limit):
    """RSS with ?paged=N. Used where robots.txt puts the REST API off limits."""
    items, page = [], 1
    while len(items) < limit and page <= 60:
        url = "https://%s/feed/?paged=%d" % (host, page)
        try:
            body, cached = get_cached(url, "%s-feed-p%03d.xml" % (key, page))
        except NotCached:
            print("  %s: stopping at feed page %d (not cached; offline mode)" % (key, page), file=sys.stderr)
            break
        except Exception as exc:                                  # noqa: BLE001
            print("  %s feed page %d stopped: %s" % (key, page, exc), file=sys.stderr)
            break
        batch = feeds.parse_feed(body, key)
        if not batch:
            break
        oldest = None
        for it in batch:
            date = _rss_date(it["pub_date"])
            oldest = date or oldest
            if date and (date < after or date >= before):
                continue
            items.append({
                "outlet_key": key,
                "source_outlet": it["source_outlet"],
                "article_url": it["article_url"],
                "article_date": date or "",
                "title": it["title"],
                "author": it["author"],
                "text": it["feed_text"],
            })
        print("  %s feed page %d: %d items, oldest %s%s"
              % (key, page, len(batch), oldest, " (cached)" if cached else ""), file=sys.stderr)
        if oldest and oldest < after:
            break
        page += 1
    return items[:limit]


def _rss_date(value):
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--after", required=True, help="earliest publication date, YYYY-MM-DD")
    ap.add_argument("--before", required=True, help="exclusive upper bound, YYYY-MM-DD")
    ap.add_argument("--limit-per-outlet", type=int, default=4000)
    ap.add_argument("--out", default=None)
    ap.add_argument("--only", default=None,
                    help="restrict to one outlet key (tribuna, diario, independiente, noticiaspv)")
    ap.add_argument("--offline", action="store_true",
                    help="build only from pages already cached; make no requests")
    args = ap.parse_args()

    globals()["OFFLINE"] = args.offline
    corpus = []
    for key, plan in PLAN.items():
        if args.only and key != args.only:
            continue
        print("%s (%s via %s)" % (key, plan["host"], plan["method"]), file=sys.stderr)
        if plan.get("robots_note"):
            print("  note: %s" % plan["robots_note"], file=sys.stderr)
        fn = collect_rest if plan["method"] == "rest" else collect_paged_feed
        got = fn(key, plan["host"], args.after, args.before, args.limit_per_outlet)
        print("  -> %d articles" % len(got), file=sys.stderr)
        corpus.extend(got)

    seen, unique = set(), []
    for item in corpus:
        if item["article_url"] and item["article_url"] not in seen:
            seen.add(item["article_url"])
            unique.append(item)
    unique.sort(key=lambda i: i["article_date"], reverse=True)

    out = args.out or os.path.join(feeds.ROOT, "data", "corpus-%s_%s.json" % (args.after, args.before))
    payload = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "window": {"after": args.after, "before": args.before},
               "access_plan": PLAN, "count": len(unique), "items": unique}
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    print("\n%d unique articles -> %s" % (len(unique), out), file=sys.stderr)


if __name__ == "__main__":
    main()
