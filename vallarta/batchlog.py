#!/usr/bin/env python3
"""Append a finished batch to the archive progress file, safely.

Two sessions are reading the corpus in parallel, so the progress file is a
shared resource. This does a locked read-modify-write instead of the
read-in-one-process, write-in-another pattern that silently loses batches.

  python3 batchlog.py --batch archive-2026-08-24-b051 \
      --triage data/triage-archive-2026-08-24-b051.json

Counts are derived from the triage file — the file that records what was
actually read — rather than being retyped by hand.
"""

import argparse
import fcntl
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
PROGRESS = os.path.join(DATA, "archive-progress-2026-08-24.json")

# The verdicts a triage decision may carry. Defined once and imported by the
# things that count them, because a verdict that a counter does not recognise
# falls into whatever its else-branch is — which is how batch b022 reported 14
# real complaints as exclusions. Adding a value here means teaching every
# counter about it in the same change.
VERDICTS = ("yes", "unsure", "no", "unprocessed")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch", required=True)
    ap.add_argument("--triage", required=True)
    ap.add_argument("--extract", default="")
    args = ap.parse_args()

    triage = json.load(open(os.path.join(ROOT, args.triage), encoding="utf-8"))
    decisions = triage["decisions"]

    # A batch that read nothing is never a valid outcome. It happens when an
    # agent finds its assigned URLs already in processed_urls and concludes
    # there is nothing to do — but "already in processed_urls" is not evidence
    # of a read, and logging the empty batch converts that assumption into a
    # permanent gap: the articles stay marked processed, so the reading queue
    # skips them forever, and no decision exists anywhere. Four batches did
    # exactly this and stranded 238 articles.
    if not decisions:
        raise SystemExit(
            "%s contains no decisions.\n"
            "If its articles are genuinely already triaged, the batch does not need "
            "logging. If they are only listed in processed_urls with no decision "
            "behind them, they are unread and stranded — requeue them instead of "
            "logging an empty batch. Check with: python3 readqueue.py audit" % args.triage)
    # "unprocessed" is the honest verdict for the near-empty corpus stubs that
    # cannot be read and (fetch-once) cannot be re-fetched. It is only valid
    # for an article that was NOT read — a read article gets a real verdict.
    for d in decisions:
        if d.get("decision") == "unprocessed" and d.get("read_by_agent"):
            raise SystemExit("decision 'unprocessed' with read_by_agent true on %s"
                             % d.get("article_url"))

    # A decision outside the enum is counted as an exclusion by every consumer in
    # the pipeline, so a typo silently buries qualifying articles. It did: batch
    # b022 wrote "qualified" instead of "yes" and reported 14 real complaints as
    # excluded for half a day. Refuse the batch instead of logging a wrong count.
    bad = sorted({d.get("decision") for d in decisions} - set(VERDICTS))
    if bad:
        raise SystemExit("%s: decision values outside %s: %s\n"
                         "Fix the triage file; do not log a batch whose verdicts cannot be counted."
                         % (args.triage, "/".join(VERDICTS), ", ".join(repr(b) for b in bad)))
    missing = [d["article_url"] for d in decisions if "read_by_agent" not in d]
    if missing:
        raise SystemExit("%s: %d decisions do not say whether the article was read.\n"
                         "Nothing is screened out any more, so every decision must record "
                         "read_by_agent explicitly." % (args.triage, len(missing)))

    read = sum(1 for d in decisions if d.get("read_by_agent"))
    qualified = sum(1 for d in decisions if d.get("decision") == "yes")
    unsure = sum(1 for d in decisions if d.get("decision") == "unsure")
    # An unprocessed article was not judged at all. Folding it into "excluded"
    # would report a stub nobody could read as a considered rejection.
    unprocessed = sum(1 for d in decisions if d.get("decision") == "unprocessed")
    entry = {
        "batch": args.batch,
        "queue_kind": triage.get("metadata", {}).get("queue_kind", "full-read"),
        "scanned": len(decisions), "read": read,
        "qualified": qualified, "unsure": unsure,
        "excluded": len(decisions) - qualified - unsure - unprocessed,
        "triage_file": args.triage,
    }
    if unprocessed:
        entry["unprocessed"] = unprocessed
    if args.extract:
        entry["extract_file"] = args.extract
    if read != len(decisions):
        entry["unread"] = len(decisions) - read

    with open(PROGRESS, "r+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        progress = json.load(fh)
        known = {b["batch"] for b in progress["batches"]}
        if entry["batch"] in known:
            fcntl.flock(fh, fcntl.LOCK_UN)
            raise SystemExit("batch %s is already logged" % entry["batch"])
        progress["batches"].append(entry)
        urls = dict.fromkeys(progress.get("processed_urls", []))
        for d in decisions:
            urls[d["article_url"]] = None
        progress["processed_urls"] = list(urls)
        progress["processed_count"] = len(urls)
        progress["last_updated"] = entry["batch"]
        fh.seek(0)
        json.dump(progress, fh, ensure_ascii=False, indent=1)
        fh.truncate()
        fcntl.flock(fh, fcntl.LOCK_UN)

    print("%s logged: %d read, %d qualified, %d unsure, %d excluded%s | corpus %d/%d"
          % (entry["batch"], read, qualified, unsure, entry["excluded"],
             ", %d unprocessed" % unprocessed if unprocessed else "",
             len(urls), progress.get("total_articles", 0)))


if __name__ == "__main__":
    main()
