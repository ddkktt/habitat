"""Tiny stdlib-only server for the Puerto Vallarta complaint dashboard.

Serves web/ as static files and the collected dataset at /api/data. The data is
read fresh from disk on every request, so the page reflects the latest cycle as
soon as `cycle.py` has run — there is nothing to rebuild or republish.

This server is a viewer. It never fetches from the news sites; only feeds.py does
that, under the rate limits in vallarta_agent_prompt.md.

Run:  python3 server.py [--port 8000] [--no-browser]
"""

import argparse
import glob
import json
import os
import re
import webbrowser
from collections import Counter
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import store

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(ROOT, "web")
STATE = os.path.join(ROOT, "state")
REPORTS = os.path.join(ROOT, "reports")
PREFIX = "" if store.CITY == "vallarta" else "%s-" % store.CITY


def _logged_batches():
    """Batch ids the archive progress files say they have logged."""
    ids = set()
    for path in glob.glob(os.path.join(store.DATA, "archive-progress-*.json")):
        ids.update(b["batch"] for b in store.load(path, {}).get("batches", []))
    return ids


def _triage_files():
    """Every triage file, tagged by what it is.

    Classification is by whether the progress file logged the id as an archive
    batch — not by which key the id is under. Writers disagree about that: some
    batch files carry `batch`, others carry `cycle` holding a batch id. Keying
    off the field name put 111 archive batches into the daily trend line, and
    requiring `cycle` to exist crashed the dashboard outright.
    """
    batches = _logged_batches()
    for path in sorted(glob.glob(os.path.join(store.DATA, "%striage-*.json" % PREFIX))):
        triage = store.load(path, None)
        if not triage or not isinstance(triage.get("decisions"), list):
            continue
        ident = triage.get("batch") or triage.get("cycle")
        if not ident:
            yield "other", ident, triage
        elif ident in batches:
            yield "batch", ident, triage
        elif triage.get("batch") or "archive" in str(ident):
            # An archive batch written but not yet logged: an agent between
            # writing its file and logging it. Not a daily cycle, and counting
            # it as one is how this function crashed the dashboard twice.
            yield "pending", ident, triage
        else:
            yield "cycle", ident, triage


def _cycles():
    """Per-cycle triage totals, oldest first — the numbers the trend line uses.

    Daily cycles only. Archive batches are hundreds of rows against one date and
    would swamp the trend; they are summarised in the reading panel instead.
    """
    out = []
    for kind, ident, triage in _triage_files():
        if kind != "cycle":
            continue
        decisions = triage["decisions"]
        counts = Counter(d["decision"] for d in decisions)
        out.append({
            "cycle": ident,
            "scanned": triage.get("scanned", len(decisions)),
            "read": sum(1 for d in decisions if d.get("read_by_agent", True)),
            "qualified": counts["yes"],
            "unsure": counts["unsure"],
            "excluded": counts["no"],
            "fetched": sum(1 for d in decisions if d.get("full_page_fetched")),
            "exclusion_reasons": Counter(d["reason_code"] for d in decisions
                                         if d["decision"] == "no").most_common(),
        })
    return out


def _batches():
    """What the archive backfill has actually read, aggregated across batches."""
    read = qualified = unsure = excluded = unprocessed = unread = 0
    reasons, batches = Counter(), 0
    for kind, ident, triage in _triage_files():
        if kind != "batch":
            continue
        batches += 1
        for d in triage["decisions"]:
            if d.get("read_by_agent", True):
                read += 1
            else:
                unread += 1
            verdict = d.get("decision")
            if verdict == "yes":
                qualified += 1
            elif verdict == "unsure":
                unsure += 1
            elif verdict == "unprocessed" or d.get("unprocessed"):
                # Not judged at all: a corpus stub with no readable text. It is
                # not an exclusion and its reason does not belong in the
                # exclusion breakdown, which describes considered rejections.
                unprocessed += 1
            else:
                excluded += 1
                reasons[d.get("reason_code", "sin código")] += 1
    if not batches:
        return None
    pending = sum(1 for kind, _, _ in _triage_files() if kind == "pending")
    return {"batches": batches, "read": read, "triaged_unread": unread,
            "qualified": qualified, "unsure": unsure, "excluded": excluded,
            "unprocessed": unprocessed, "pending_unlogged": pending,
            "exclusion_reasons": reasons.most_common()}


# The ranked files written before 2026-08-24 label their tiers read / maybe /
# screened_out. Those names described a filter that no longer exists; the tiers
# now mean nothing but reading order, and map 1:1 onto the new names.
TIER = {"read": "priority_high", "maybe": "priority_medium", "screened_out": "priority_low"}


def _processed_urls():
    """Every corpus URL that has actually been read and triaged."""
    done = set()
    for path in glob.glob(os.path.join(store.DATA, "archive-progress-*.json")):
        done.update(store.load(path, {}).get("processed_urls", []))
    return done


def _reading():
    """Progress through the corpus: read so far vs not yet read.

    Operator decision, 2026-08-24: nothing is screened out. This panel used to
    show a filter funnel with a "discarded unread" pile; there is no such pile.
    What it shows now is how much of the corpus has actually been read, because
    that — not a score distribution — is what tells a reader how far to trust
    the counts elsewhere in the dashboard.
    """
    paths = sorted(glob.glob(os.path.join(store.DATA, "%sranked-*.json" % PREFIX)))
    if not paths:
        return None
    ranked = store.load(paths[-1], None)
    if not ranked:
        return None
    items = ranked["items"]
    done = _processed_urls()
    unread = [r for r in items if r["article_url"] not in done]
    read_n = len(items) - len(unread)

    tiers = Counter(TIER.get(r["bucket"], r["bucket"]) for r in items)
    tiers_unread = Counter(TIER.get(r["bucket"], r["bucket"]) for r in unread)
    outlets = Counter(r["source_outlet"] for r in items)
    outlets_unread = Counter(r["source_outlet"] for r in unread)
    return {
        "file": os.path.basename(paths[-1]),
        "window": ranked.get("window"),
        "total": ranked["total"],
        "read": read_n,
        "unread": len(unread),
        "pct_read": round(100.0 * read_n / max(ranked["total"], 1), 1),
        "tiers": dict(tiers),
        "tiers_unread": dict(tiers_unread),
        "batches": _batches(),
        "by_outlet": outlets.most_common(),
        "unread_by_outlet": [(name, outlets_unread.get(name, 0)) for name, _ in outlets.most_common()],
        "categories_in_corpus": Counter(c for r in items for c in r["categories_hit"]).most_common(),
        "next_to_read": [
            {k: r[k] for k in ("article_url", "article_date", "source_outlet",
                               "title", "score", "reason")}
            | {"bucket": TIER.get(r["bucket"], r["bucket"])}
            for r in unread[:40]
        ],
    }


_ARTICLES = {"path": None, "mtime": 0, "rows": []}


def _articles():
    """All scored articles, slimmed and cached in memory until the file changes.

    The ranked file runs to megabytes, so rows are filtered and paged here rather
    than shipped whole to the browser.
    """
    paths = sorted(glob.glob(os.path.join(store.DATA, "%sranked-*.json" % PREFIX)))
    if not paths:
        return []
    path = paths[-1]
    mtime = os.path.getmtime(path)
    if _ARTICLES["path"] == path and _ARTICLES["mtime"] == mtime:
        return _ARTICLES["rows"]
    ranked = store.load(path, {"items": []})
    rows = []
    for r in ranked["items"]:
        rows.append({
            "url": r["article_url"], "date": r["article_date"], "outlet": r["source_outlet"],
            "title": r["title"], "author": r.get("author"), "score": r["score"],
            "bucket": r["bucket"], "reason": r["reason"],
            "categories": sorted(r["categories_hit"]), "signals": r["signals"],
            "snippet": (r["snippets"] or [None])[0],
            "hay": (" ".join([r["title"], r["source_outlet"], r["article_url"]]
                             + list(r["categories_hit"]) + r["signals"])).lower(),
        })
    _ARTICLES.update({"path": path, "mtime": mtime, "rows": rows})
    return rows


def _article_page(query):
    rows = _articles()
    q = (query.get("q") or [""])[0].strip().lower()
    bucket = (query.get("bucket") or [""])[0]
    category = (query.get("category") or [""])[0]
    outlet = (query.get("outlet") or [""])[0]
    frm = (query.get("from") or [""])[0]
    to = (query.get("to") or [""])[0]
    has_record = (query.get("recorded") or [""])[0] == "1"

    recorded = {r["article_url"] for r in store.load(store.RECORDS, [])}
    out = []
    for r in rows:
        if q and q not in r["hay"]:
            continue
        if bucket and r["bucket"] != bucket:
            continue
        if category and category not in r["categories"]:
            continue
        if outlet and r["outlet"] != outlet:
            continue
        if frm and r["date"] < frm:
            continue
        if to and r["date"] > to:
            continue
        if has_record and r["url"] not in recorded:
            continue
        out.append(r)

    sort = (query.get("sort") or ["score"])[0]
    if sort == "date":
        out.sort(key=lambda r: (r["date"], r["score"]), reverse=True)
    elif sort == "date_asc":
        out.sort(key=lambda r: (r["date"], r["score"]))
    else:
        out.sort(key=lambda r: (r["score"], r["date"]), reverse=True)

    try:
        per = max(10, min(200, int((query.get("per") or ["50"])[0])))
        page = max(1, int((query.get("page") or ["1"])[0]))
    except ValueError:
        per, page = 50, 1
    start = (page - 1) * per
    window = out[start:start + per]
    for r in window:
        r = r.copy()
    return {
        "total": len(out), "page": page, "per": per,
        "pages": max(1, (len(out) + per - 1) // per),
        "facets": {
            "buckets": Counter(r["bucket"] for r in out).most_common(),
            "outlets": Counter(r["outlet"] for r in out).most_common(),
            "categories": Counter(c for r in out for c in r["categories"]).most_common(),
        },
        "items": [{k: v for k, v in r.items() if k != "hay"} | {"recorded": r["url"] in recorded}
                  for r in window],
    }


def _latest_report():
    paths = sorted(glob.glob(os.path.join(REPORTS, "%sreport-*.md" % PREFIX)))
    if not paths:
        return None
    with open(paths[-1], encoding="utf-8") as fh:
        return {"cycle": re.search(r"report-(.+)\.md$", paths[-1]).group(1), "markdown": fh.read()}


def build_payload():
    records = store.load(store.RECORDS, [])
    incidents = store.load(store.INCIDENTS, [])
    by_url = {}
    for rec in records:
        by_url.setdefault(rec.get("incident_id"), []).append(rec)

    # attach each incident's records so the page needs one request, not N
    for inc in incidents:
        inc["records"] = by_url.get(inc["incident_id"], [])

    certainty = Counter(r["location_certainty"] for r in records)
    total = max(len(records), 1)
    gaz = store.load(os.path.join(STATE, "%sgazetteer.json" % PREFIX),
                     {"streets": {}, "colonias": {}, "landmarks": {}})

    return {
        "incidents": sorted(incidents, key=lambda i: (i["last_article_date"], i["incident_id"]), reverse=True),
        "records": records,
        "cycles": _cycles(),
        "totals": {
            "incidents": len(incidents),
            "records": len(records),
            "qualified": sum(1 for r in records if r["qualifies"] == "yes"),
            "unsure": sum(1 for r in records if r["qualifies"] == "unsure"),
            "located_share": round(100.0 * (certainty["exact"] + certainty["approximate"]) / total),
            "certainty": dict(certainty),
        },
        "gazetteer": {kind: sorted((v["display"] for v in bucket.values()), key=str.lower)
                      for kind, bucket in gaz.items()},
        "city": store.CITY,
        "colonia_coords": store.load(os.path.join(STATE, "colonia_coords.json"), {}),
        "vocabulary": store.load(os.path.join(STATE, "vocabulary.json"), {}),
        "candidate_sources": store.load(os.path.join(STATE, "candidate_sources.json"), {}),
        "coverage": store.load(os.path.join(STATE, "%scoverage.json" % PREFIX), {}),
        "reading": _reading(),
        "corpus": (lambda rows: {
            "count": len(rows),
            "first": min((r["date"] for r in rows), default=None),
            "last": max((r["date"] for r in rows), default=None),
            "outlets": Counter(r["outlet"] for r in rows).most_common(),
        } if rows else None)(_articles()),
        "audits": store.load(os.path.join(store.DATA, "%saudits.json" % PREFIX), []),
        "report": _latest_report(),
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/articles":
            try:
                self.send_json(_article_page(parse_qs(parsed.query)))
            except Exception as exc:                       # noqa: BLE001
                self.send_json({"error": "Could not read the article index: %s" % exc}, 500)
            return
        if parsed.path == "/api/data":
            try:
                self.send_json(build_payload())
            except Exception as exc:                       # noqa: BLE001 - surface to the UI
                self.send_json({"error": "No se pudo leer el conjunto de datos: %s" % exc}, 500)
        else:
            super().do_GET()

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            super().log_message(fmt, *args)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    url = "http://localhost:%d/" % args.port
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("Vallarta complaint dashboard → %s  (Ctrl-C to stop)" % url)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
        server.server_close()


if __name__ == "__main__":
    main()
