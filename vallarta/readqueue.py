#!/usr/bin/env python3
"""The full-corpus reading queue.

Operator decision, 2026-08-24: nothing is screened out. Every article in
`data/corpus-pv.json` is read as full text and triaged. `data/ranked-pv.json`
survives only as *reading order* — the highest-scoring articles are read first
so that the qualifying records land early, but a low score never excuses a
missing read.

  python3 readqueue.py status
  python3 readqueue.py next --n 25              # from the front (highest score)
  python3 readqueue.py next --n 25 --from-end   # from the back (lowest score)
  python3 readqueue.py audit                    # reconcile progress against the triage files

`next` prints the full article text for each entry and writes the slice to
`state/queue-slice-<label>.json` so the triage file can be written against the
exact articles that were printed. Nothing here makes a qualification decision.
"""

import argparse
import glob
import json
import os
from collections import Counter, defaultdict

import batchlog

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
STATE = os.path.join(ROOT, "state")
PROGRESS = os.path.join(DATA, "archive-progress-2026-08-24.json")
RANKED = os.path.join(DATA, "ranked-pv.json")
CORPUS = os.path.join(DATA, "corpus-pv.json")


def load():
    ranked = json.load(open(RANKED, encoding="utf-8"))["items"]
    corpus = json.load(open(CORPUS, encoding="utf-8"))["items"]
    by_url = {c["article_url"]: c for c in corpus}
    progress = json.load(open(PROGRESS, encoding="utf-8"))
    done = set(progress.get("processed_urls", []))
    return ranked, by_url, progress, done


def remaining(ranked, done):
    return [(i, r) for i, r in enumerate(ranked) if r["article_url"] not in done]


def status(args):
    ranked, by_url, progress, done = load()
    rest = remaining(ranked, done)
    total = len(ranked)
    print("corpus            %s" % progress.get("corpus"))
    print("articles in order %d" % total)
    print("read + triaged    %d (%.1f%%)" % (len(done), 100.0 * len(done) / total))
    print("not yet read      %d" % len(rest))
    if rest:
        print("front of queue    #%d  score %d  %s" % (rest[0][0], rest[0][1]["score"], rest[0][1]["article_date"]))
        print("back of queue     #%d  score %d  %s" % (rest[-1][0], rest[-1][1]["score"], rest[-1][1]["article_date"]))
    missing = [u for u in done if u not in by_url]
    if missing:
        print("processed URLs not in this corpus: %d" % len(missing))


def nxt(args):
    ranked, by_url, progress, done = load()
    rest = remaining(ranked, done)
    if not rest:
        return print("queue empty — every article in the corpus has been read")
    picks = rest[-args.n:][::-1] if args.from_end else rest[: args.n]

    slice_rows = []
    for idx, r in picks:
        art = by_url.get(r["article_url"])
        text = (art or {}).get("text") or ""
        slice_rows.append({
            "queue_index": idx, "article_url": r["article_url"],
            "article_date": r["article_date"], "source_outlet": r["source_outlet"],
            "title": r["title"], "author": (art or {}).get("author"),
            "bucket": r["bucket"], "score": r["score"], "chars": len(text),
            "text_available": bool(text.strip()),
        })

    if args.label:
        path = os.path.join(STATE, "queue-slice-%s.json" % args.label)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(slice_rows, fh, ensure_ascii=False, indent=1)
        print("# slice -> %s" % os.path.relpath(path, ROOT))
    print("# %d of %d not-yet-read, taken from the %s of the reading order\n"
          % (len(picks), len(rest), "back" if args.from_end else "front"))

    for idx, r in picks:
        art = by_url.get(r["article_url"])
        text = (art or {}).get("text") or ""
        print("=" * 78)
        print("[#%d] %s | %s | score %d | tier %s | %d chars"
              % (idx, r["article_date"], r["source_outlet"], r["score"], r["bucket"], len(text)))
        print("URL: %s" % r["article_url"])
        print("TITLE: %s" % r["title"])
        if (art or {}).get("author"):
            print("AUTHOR: %s" % art["author"])
        body = text.strip()
        if not body:
            print("TEXT: <empty in corpus — record as text_unavailable>")
        else:
            print("TEXT: %s" % (body if not args.max_chars else body[: args.max_chars]))
            if args.max_chars and len(body) > args.max_chars:
                print("… [%d chars truncated — re-run with --max-chars 0 for the rest]"
                      % (len(body) - args.max_chars))
        print()


def audit(args):
    """Reconcile what the progress file claims against what the triage files show.

    The progress file is a summary; the triage files are the evidence. When they
    disagree, the progress file is wrong, because a read that left no decision
    row behind is not a read. Run this after a fan-out of batches — it has
    already caught a URL marked processed with no decision anywhere, a batch that
    wrote verdicts outside the enum, and 22 articles read twice.
    """
    ranked, by_url, progress, done = load()
    logged = {b["batch"] for b in progress.get("batches", [])}
    rows = defaultdict(list)
    skipped, unlogged_files = [], []
    for path in sorted(glob.glob(os.path.join(DATA, "triage-*.json"))):
        triage = json.load(open(path, encoding="utf-8"))
        # A file belongs to this backfill if the progress file logged its id.
        # Do NOT key off the field name: some writers put the batch id under
        # `batch` and others under `cycle`, and skipping the latter made 240
        # correctly-triaged articles look like claimed reads with no decision.
        ident = triage.get("batch") or triage.get("cycle")
        if ident not in logged:
            (unlogged_files if ident and "archive" in str(ident) else skipped).append(
                os.path.basename(path))
            continue
        for d in triage.get("decisions", []):
            if d["article_url"] in by_url:
                rows[d["article_url"]].append((ident, d))

    problems = 0
    orphans = sorted(u for u in done if u not in rows)
    if orphans:
        problems += len(orphans)
        print("claimed as processed, but no triage decision anywhere: %d" % len(orphans))
        for u in orphans[:20]:
            print("  %s" % u)

    unlogged = sorted(u for u in rows if u not in done and u in by_url)
    if unlogged:
        problems += len(unlogged)
        print("triaged, but missing from processed_urls: %d" % len(unlogged))
        for u in unlogged[:20]:
            print("  %s  (%s)" % (u, ", ".join(b for b, _ in rows[u])))

    bad = Counter()
    for u, entries in rows.items():
        for batch, d in entries:
            if d.get("decision") not in batchlog.VERDICTS:
                bad[(batch, d.get("decision"))] += 1
    if bad:
        problems += sum(bad.values())
        print("decisions outside yes/unsure/no: %d" % sum(bad.values()))
        for (batch, value), n in bad.most_common():
            print("  %s: %r x%d — counted as exclusions by every consumer" % (batch, value, n))

    # An article whose verdict is "unprocessed" is legitimately unread: the
    # corpus carries no text for it and the fetch-once rule forbids re-fetching.
    # An article with a real verdict and no read is the defect.
    stubs = [(u, b) for u, entries in rows.items() for b, d in entries
             if d.get("decision") == "unprocessed" or d.get("unprocessed")]
    unread = [(u, b) for u, entries in rows.items() for b, d in entries
              if not d.get("read_by_agent", False)
              and d.get("decision") != "unprocessed" and not d.get("unprocessed")]
    if unread:
        problems += len(unread)
        print("judged without a full-text read: %d — a verdict with no reading behind it"
              % len(unread))
        for u, b in unread[:20]:
            print("  %s  (%s)" % (u, b))
    if stubs:
        print("recorded unprocessed (no readable text in the corpus, cannot be "
              "re-fetched): %d — not a defect, but not read either" % len(stubs))
        for u, b in stubs[:10]:
            print("  %s  (%s)" % (u, b))

    # A logged batch whose triage file holds fewer decisions than the count it
    # was logged with has lost evidence since it was logged — a second agent
    # writing the same path overwrote it. The reads may be recoverable, but the
    # file no longer shows them, and the batch reads as smaller than it was.
    shrunk = []
    counts = defaultdict(int)
    for entries in rows.values():
        for ident, _ in entries:
            counts[ident] += 1
    superseded = []
    for b in progress.get("batches", []):
        if b.get("superseded_by"):
            superseded.append((b["batch"], b["superseded_by"]))
            continue
        claimed = b.get("scanned")
        actual = counts.get(b["batch"], 0)
        if claimed is not None and actual != claimed:
            shrunk.append((b["batch"], claimed, actual))
    if shrunk:
        problems += len(shrunk)
        print("logged count disagrees with the triage file: %d" % len(shrunk))
        for ident, claimed, actual in shrunk:
            print("  %-38s logged scanned=%-3d but the file holds %d decision(s)"
                  % (ident, claimed, actual))

    if superseded:
        print("logged twice, counts moved to the surviving entry: %d (not an error)"
              % len(superseded))
        for ident, keeper in superseded:
            print("  %-38s -> %s" % (ident, keeper))

    dupes = {u: e for u, e in rows.items() if len(e) > 1}
    if dupes:
        disagree = {u: e for u, e in dupes.items()
                    if len({(d["decision"], d.get("reason_code")) for _, d in e}) > 1}
        print("read more than once: %d (wasted effort, not an error)" % len(dupes))
        print("  of those, the reads disagreed: %d" % len(disagree))
        for u, e in list(disagree.items())[:10]:
            print("  %s" % u)
            for b, d in e:
                print("      %-32s %s / %s" % (b, d["decision"], d.get("reason_code")))

    if unlogged_files:
        problems += len(unlogged_files)
        print("archive triage files never logged to the progress file: %d" % len(unlogged_files))
        for name in unlogged_files[:20]:
            print("  %s — its articles are not counted as read anywhere" % name)
    if skipped:
        print("not part of this corpus backfill, not reconciled: %s" % ", ".join(skipped))
    print("\n%d article(s) read and triaged of %d in the corpus; %d not yet read"
          % (len(done), len(ranked), len(ranked) - len(done)))
    print("%s" % ("clean: the progress file and the triage files agree" if not problems
                  else "%d discrepancy/ies above need resolving" % problems))
    return 1 if problems else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status"); s.set_defaults(fn=status)
    n = sub.add_parser("next")
    n.add_argument("--n", type=int, default=25)
    n.add_argument("--from-end", action="store_true")
    n.add_argument("--label", default="")
    n.add_argument("--max-chars", type=int, default=0, help="0 means the whole article")
    n.set_defaults(fn=nxt)
    a = sub.add_parser("audit"); a.set_defaults(fn=audit)
    args = ap.parse_args()
    raise SystemExit(args.fn(args) or 0)


if __name__ == "__main__":
    main()
