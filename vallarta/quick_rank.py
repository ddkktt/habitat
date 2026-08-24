#!/usr/bin/env python3
"""Fast, compact ranking for large keyword backfill corpora.

This is deliberately simpler than `prefilter.py`: it uses accent-folded
substring matches and writes compact records. It sets reading *order* only.
Operator decision, 2026-08-24: every article is read as full text and triaged,
so `priority_low` means "read this last", never "skip this". Its tiers are not
extraction decisions and must never be reported as verdicts.
"""

import argparse
import json
import os
from collections import Counter

import prefilter
import store

STATE = os.path.join(store.ROOT, "state")


def terms():
    vocab = store.load(os.path.join(STATE, "vocabulary.json"), {})
    active = vocab.get("active", {})
    cats = {
        cat: [(term, prefilter.fold(term)) for term in values]
        for cat, values in active.items()
        if cat != "complaint_signals"
    }
    signals = [(term, prefilter.fold(term)) for term in active.get("complaint_signals", [])]
    anti = [(term, prefilter.fold(term)) for term in vocab.get("anti_keywords", {}).get("terms", [])]
    local = [(term, prefilter.fold(term)) for term in prefilter.LOCAL_TERMS]
    gaz = store.load(os.path.join(STATE, "gazetteer.json"), {})
    local += [(v["display"], prefilter.fold(v["display"]))
              for bucket in gaz.values() for v in bucket.values()]
    return cats, signals, anti, local


def hits(pairs, folded):
    return [raw for raw, needle in pairs if needle and needle in folded]


def rank(item, cats, signals, anti, local, max_chars):
    blob = "%s\n%s" % (item.get("title", ""), item.get("text", ""))
    folded = prefilter.fold(blob[:max_chars] if max_chars else blob)
    cat_hits = {cat: hits(pairs, folded) for cat, pairs in cats.items()}
    cat_hits = {cat: values for cat, values in cat_hits.items() if values}
    signal_hits = hits(signals, folded)
    anti_hits = hits(anti, folded)
    local_hits = hits(local, folded)
    score = (2 * sum(len(v) for v in cat_hits.values())
             + 3 * len(signal_hits)
             + len(local_hits)
             - 3 * len(anti_hits))
    if not cat_hits:
        bucket, reason = "priority_low", "sin vocabulario de infraestructura"
    elif not local_hits:
        bucket, reason = "priority_low", "sin señal local"
    elif anti_hits and not signal_hits and score < 6:
        bucket, reason = "priority_low", "dominan palabras excluyentes"
    elif signal_hits:
        bucket, reason = "priority_high", "señal de queja + infraestructura + local"
    else:
        bucket, reason = "priority_medium", "infraestructura + local, sin queja explícita"
    return {
        "article_url": item["article_url"],
        "article_date": item.get("article_date", ""),
        "source_outlet": item["source_outlet"],
        "title": item.get("title", ""),
        "bucket": bucket,
        "reason": reason,
        "score": score,
        "categories_hit": cat_hits,
        "signals": signal_hits,
        "local": local_hits[:8],
        "anti": anti_hits,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("corpus")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-chars", type=int, default=3000)
    args = ap.parse_args()

    corpus = json.load(open(args.corpus, encoding="utf-8"))
    cats, signals, anti, local = terms()
    ranked = [rank(item, cats, signals, anti, local, args.max_chars)
              for item in corpus["items"]]
    ranked.sort(key=lambda r: (-r["score"], r["article_date"]))
    buckets = Counter(r["bucket"] for r in ranked)
    payload = {
        "corpus": os.path.basename(args.corpus),
        "window": corpus.get("window"),
        "total": len(ranked),
        "buckets": dict(buckets),
        "ranker": "quick substring ranker; sets reading order only — every article is read",
        "items": ranked,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"), ensure_ascii=False)
    print("%d articles ranked -> %s" % (len(ranked), args.out))
    print("all %d are to be read; the tiers below are reading order only" % len(ranked))
    for name in ("priority_high", "priority_medium", "priority_low"):
        print("  %-15s %5d" % (name, buckets[name]))


if __name__ == "__main__":
    main()
