#!/usr/bin/env python3
"""The audit that keeps the pipeline honest.

The `screened` draw is retired. It sampled the pile of articles the agent never
read, to catch a filter that was swallowing real complaints. Operator decision,
2026-08-24: nothing is screened out any more — every article is read — so there
is no pile to sample. Past `screened` audits stay in data/audits.json as a
record of what was checked while the rule was in force.

  python3 sample.py records --n 10 --seed 1
      The weekly quality check: draw records for re-reading against their source
      article. Target accuracy is 90%; below that, stop and report.

It prints what to read. The verdict is a judgement and gets written back with
`sample.py verdict`, never guessed here.
"""

import argparse
import json
import os
import random
import sys

import store

AUDITS = os.path.join(store.DATA, "audits.json")


def records(args):
    pool = store.load(store.RECORDS, [])
    if len(pool) < args.n:
        print("only %d records exist; the weekly check wants %d. Not enough data yet."
              % (len(pool), args.n), file=sys.stderr)
    rng = random.Random(args.seed)
    picks = rng.sample(pool, min(args.n, len(pool)))
    print("# Record quality check — %d of %d, seed %d\n" % (len(picks), len(pool), args.seed))
    for i, rec in enumerate(picks, 1):
        print("%2d. %s" % (i, rec["article_url"]))
        print("    summary:   %s" % rec["summary"])
        print("    place:     street=%s colonia=%s landmark=%s (%s)"
              % (rec["street"], rec["colonia"], rec["landmark"], rec["location_certainty"]))
        print("    evidence:  %s" % rec["location_evidence"])
        print("    cats/status: %s / %s" % (", ".join(rec["categories"]), rec["status"]))
        print()
    print("Re-read each source article and confirm every field. Then:\n"
          "  python3 sample.py verdict --kind records --checked %d --misses <n> --note '...'"
          % len(picks))


def verdict(args):
    audits = store.load(AUDITS, [])
    accuracy = round(100.0 * (args.checked - args.misses) / max(args.checked, 1), 1)
    audits.append({"kind": args.kind, "cycle": args.cycle, "seed": args.seed,
                   "checked": args.checked, "misses": args.misses,
                   "accuracy_pct": accuracy, "note": args.note})
    store.save(AUDITS, audits)
    print("recorded: %s %d checked, %d missed, %.1f%% accurate" %
          (args.kind, args.checked, args.misses, accuracy))
    if args.kind == "records" and accuracy < 90:
        print("\nBELOW THE 90% TARGET. The prompt says stop and report rather than\n"
              "continue producing unreliable data.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s2 = sub.add_parser("records")
    s2.add_argument("--n", type=int, default=10); s2.add_argument("--seed", type=int, default=1)
    s2.set_defaults(fn=records)

    s3 = sub.add_parser("verdict")
    # "screened" stays accepted so the retired audits in audits.json keep one vocabulary
    s3.add_argument("--kind", choices=["screened", "records"], required=True)
    s3.add_argument("--checked", type=int, required=True)
    s3.add_argument("--misses", type=int, required=True)
    s3.add_argument("--cycle", default="")
    s3.add_argument("--seed", type=int, default=1)
    s3.add_argument("--note", default="")
    s3.set_defaults(fn=verdict)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
