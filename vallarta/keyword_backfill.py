#!/usr/bin/env python3
"""Keyword-first archive backfill for likely infrastructure complaints.

This builds a corpus for `prefilter.py` without crawling every article first.

Access plan:
  * Tribuna de la Bahia and Diario de Vallarta: WordPress REST search, allowed
    by robots.txt at the time this script was added.
  * Vallarta Independiente: robots.txt disallows /wp-json/, so use the public
    sitemap to find URLs whose slugs contain infrastructure terms, then fetch
    only those matching article pages.

The output is a normal corpus JSON:

  python3 keyword_backfill.py --after 2017-06-22 --before 2026-08-25
  python3 prefilter.py data/keyword-corpus-2017-06-22_2026-08-25.json \
      --out data/keyword-ranked-2017-06-22_2026-08-25.json
"""

import argparse
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime, timezone

import feeds
import prefilter
import store

ROOT = feeds.ROOT
CACHE = os.path.join(ROOT, "cache", "keyword-backfill")
STATE = os.path.join(ROOT, "state")
DATA = os.path.join(ROOT, "data")

REST_SOURCES = {
    "tribuna": "tribunadelabahia.com.mx",
    "diario": "diariodevallarta.com",
}

SITEMAP_SOURCES = {
    "independiente": {
        "index": "https://vallartaindependiente.com/sitemap.xml",
        "robots_note": "robots.txt disallows /wp-json/; using sitemap plus article pages",
    },
}

PER_PAGE = 100


def cache_path(name):
    os.makedirs(CACHE, exist_ok=True)
    return os.path.join(CACHE, name)


def get_cached(url, name):
    path = cache_path(name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read(), True
    body = feeds.get(url)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return body, False


def wanted_terms(limit=None):
    vocab = store.load(os.path.join(STATE, "vocabulary.json"), {})
    active = vocab.get("active", {})
    signal_terms = []
    category_terms = []
    for category, values in active.items():
        for value in values:
            folded = prefilter.fold(value)
            if len(folded) >= 4:
                if category == "complaint_signals":
                    signal_terms.append(value)
                else:
                    category_terms.append(value)
    # Short single words like "agua" are useful, but very broad. Put phrases
    # first so high-signal requests run before broad requests when capped.
    category_terms = sorted(set(category_terms), key=lambda t: (-(" " in t), -len(t), t.lower()))
    signal_terms = sorted(set(signal_terms), key=lambda t: (-(" " in t), -len(t), t.lower()))
    terms = signal_terms + [t for t in category_terms if t not in set(signal_terms)]
    return terms[:limit] if limit else terms


def post_item(key, post):
    return {
        "outlet_key": key,
        "source_outlet": feeds.OUTLET_NAMES[key],
        "article_url": post.get("link", ""),
        "article_date": (post.get("date") or "")[:10],
        "title": feeds.strip_html(post.get("title", {}).get("rendered", "")),
        "author": None,
        "text": feeds.strip_html(post.get("content", {}).get("rendered", "")),
    }


def collect_rest(key, host, terms, after, before, request_budget, pages_per_term):
    items, requests = [], 0
    seen_ids = set()
    for term in terms:
        page = 1
        while ((request_budget is None or requests < request_budget)
               and (pages_per_term is None or page <= pages_per_term)):
            query = urllib.parse.urlencode({
                "per_page": PER_PAGE,
                "page": page,
                "orderby": "date",
                "order": "desc",
                "after": "%sT00:00:00" % after,
                "before": "%sT00:00:00" % before,
                "search": term,
                "_fields": "id,date,link,title,content,author,categories",
            })
            url = "https://%s/wp-json/wp/v2/posts?%s" % (host, query)
            name = "%s-search-%s-%s-%s-p%03d.json" % (
                key, after, before, re.sub(r"[^a-z0-9]+", "-", prefilter.fold(term)).strip("-"), page)
            try:
                body, cached = get_cached(url, name)
            except Exception as exc:                                  # noqa: BLE001
                print("  %s term %r page %d failed: %s" % (key, term, page, exc), file=sys.stderr)
                break
            requests += 0 if cached else 1
            try:
                batch = json.loads(body)
            except json.JSONDecodeError:
                print("  %s term %r page %d returned non-JSON" % (key, term, page), file=sys.stderr)
                break
            if not isinstance(batch, list) or not batch:
                break
            added = 0
            for post in batch:
                if post.get("id") in seen_ids:
                    continue
                seen_ids.add(post.get("id"))
                items.append(post_item(key, post))
                added += 1
            print("  %s search %-24r page %03d: %3d posts, %3d new%s"
                  % (key, term, page, len(batch), added, " (cached)" if cached else ""), file=sys.stderr)
            if len(batch) < PER_PAGE:
                break
            page += 1
        if request_budget is not None and requests >= request_budget:
            print("  %s request budget reached" % key, file=sys.stderr)
            break
    return items


def sitemap_locs(xml):
    return [m.group(1).strip() for m in re.finditer(r"<loc>([^<]+)</loc>", xml)]


def term_pattern(terms):
    slug_terms = []
    for term in terms:
        folded = prefilter.fold(term).replace(" ", "-")
        if len(folded) >= 4:
            slug_terms.append(re.escape(folded))
    return re.compile(r"(?:%s)" % "|".join(sorted(set(slug_terms), key=len, reverse=True)))


def collect_sitemap(key, plan, terms, after, before, sitemap_budget, article_budget):
    print("  note: %s" % plan["robots_note"], file=sys.stderr)
    index, _ = get_cached(plan["index"], "%s-sitemap-index.xml" % key)
    sitemaps = [u for u in sitemap_locs(index) if "post-sitemap" in u]
    if sitemap_budget is not None:
        sitemaps = sitemaps[:sitemap_budget]
    pat = term_pattern(terms)
    candidates = []
    for i, sm_url in enumerate(sitemaps, 1):
        body, cached = get_cached(sm_url, "%s-post-sitemap-%03d.xml" % (key, i))
        urls = [u for u in sitemap_locs(body) if pat.search(prefilter.fold(u))]
        candidates.extend(urls)
        print("  %s sitemap %03d: %4d URL matches%s"
              % (key, i, len(urls), " (cached)" if cached else ""), file=sys.stderr)

    items, seen = [], set()
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        if article_budget is not None and len(items) >= article_budget:
            print("  %s article budget reached" % key, file=sys.stderr)
            break
        try:
            body, cached = get_cached(url, "%s-page-%s.html" % (
                key, re.sub(r"[^a-z0-9]+", "-", url).strip("-")[-120:]))
        except Exception as exc:                                  # noqa: BLE001
            print("  %s article failed %s (%s)" % (key, url, exc), file=sys.stderr)
            continue
        art = feeds.extract_article(body)
        date = art.get("published") or ""
        if date and (date < after or date >= before):
            continue
        title = art["text"].splitlines()[0] if art.get("text") else ""
        items.append({
            "outlet_key": key,
            "source_outlet": feeds.OUTLET_NAMES[key],
            "article_url": url,
            "article_date": date,
            "title": title[:180],
            "author": art.get("author"),
            "text": art.get("text", ""),
        })
        print("  %s article %04d: %s%s" % (
            key, len(items), url, " (cached)" if cached else ""), file=sys.stderr)
    return items


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--after", default="2017-06-22")
    ap.add_argument("--before", default=feeds.today())
    ap.add_argument("--term-limit", type=int, default=None)
    ap.add_argument("--rest-request-budget", type=int, default=250,
                    help="new REST requests per source; cached requests do not count")
    ap.add_argument("--rest-pages-per-term", type=int, default=3,
                    help="max REST result pages to read for any one keyword")
    ap.add_argument("--sitemap-budget", type=int, default=None,
                    help="max sitemap files for sitemap-only sources")
    ap.add_argument("--article-budget", type=int, default=500,
                    help="max article pages for sitemap-only sources")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    terms = wanted_terms(args.term_limit)
    print("terms: %d" % len(terms), file=sys.stderr)
    corpus = []
    for key, host in REST_SOURCES.items():
        print("%s (%s REST search)" % (key, host), file=sys.stderr)
        corpus.extend(collect_rest(key, host, terms, args.after, args.before,
                                   args.rest_request_budget, args.rest_pages_per_term))
    for key, plan in SITEMAP_SOURCES.items():
        print("%s (sitemap URL matching)" % key, file=sys.stderr)
        corpus.extend(collect_sitemap(key, plan, terms, args.after, args.before,
                                      args.sitemap_budget, args.article_budget))

    seen, unique = set(), []
    for item in corpus:
        url = item.get("article_url")
        if url and url not in seen:
            seen.add(url)
            unique.append(item)
    unique.sort(key=lambda i: i.get("article_date") or "", reverse=True)

    out = args.out or os.path.join(DATA, "keyword-corpus-%s_%s.json" % (args.after, args.before))
    payload = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window": {"after": args.after, "before": args.before},
        "access_plan": {"rest": REST_SOURCES, "sitemap": SITEMAP_SOURCES},
        "terms": terms,
        "count": len(unique),
        "items": unique,
    }
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    print("\n%d unique keyword-matched articles -> %s" % (len(unique), out), file=sys.stderr)


if __name__ == "__main__":
    main()
