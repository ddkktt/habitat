#!/usr/bin/env python3
"""Rank a corpus into reading order. It does not decide what goes unread.

Operator decision, 2026-08-24: every article is read as full text and triaged,
at any corpus size. This scores each article against state/vocabulary.json and
sorts it into a priority tier purely so that the likely complaints are read
first:

  priority_high   - infrastructure vocabulary AND a complaint signal AND a local signal
  priority_medium - infrastructure vocabulary but a weak signal elsewhere
  priority_low    - no infrastructure vocabulary, or dominated by anti-keywords

`priority_low` is the tier that used to be called `screened_out`. The rename is
the point: a low score changes *when* an article is read, never *whether*. The
tier is not a verdict and must never be reported as one.

This also never decides that an article *qualifies*. Qualification stays a
judgement made against the article text.

  python3 prefilter.py data/corpus-1y.json --out data/ranked-1y.json

Note: `data/ranked-pv.json` was generated before this rename and still carries
the old labels (read / maybe / screened_out), which map 1:1 onto the tiers
above. It is deliberately not regenerated: it is the frozen reading order for a
read that is in progress, and rescoring it against a vocabulary that has grown
since would shuffle the queue under the readers.
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter

import store

STATE = os.path.join(store.ROOT, "state")

LOCAL_TERMS = ["puerto vallarta", "vallarta", "bahia de banderas", "bahía de banderas",
               "ixtapa", "pitillal", "las juntas", "el pitillal", "mezcales", "bucerias",
               "seapal", "ayuntamiento de puerto vallarta"]

W_CATEGORY, W_SIGNAL, W_LOCAL, W_ANTI = 2, 3, 1, -3


def fold(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower())


def compile_terms(terms):
    """Whole-word matching, accent-folded, so 'agua' does not match 'aguacate'."""
    out = []
    for term in terms:
        folded = fold(term)
        out.append((term, re.compile(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(folded))))
    return out


def load_vocab():
    vocab = store.load(os.path.join(STATE, "vocabulary.json"), {})
    active = vocab.get("active", {})
    cats = {cat: compile_terms(terms) for cat, terms in active.items() if cat != "complaint_signals"}
    signals = compile_terms(active.get("complaint_signals", []))
    anti = compile_terms(vocab.get("anti_keywords", {}).get("terms", []))
    # watch-list terms that were promoted count as active vocabulary too
    promoted = [w["term"] for w in vocab.get("watch_list", []) if w.get("promoted")]
    if promoted:
        cats.setdefault("other", []).extend(compile_terms(promoted))
    return cats, signals, anti


def gazetteer_terms():
    gaz = store.load(os.path.join(STATE, "gazetteer.json"), {})
    names = [v["display"] for bucket in gaz.values() for v in bucket.values()]
    return compile_terms(names)


def snippets(text, folded, patterns, width=110, limit=4):
    """Short windows around the matched words: enough to triage, not a reprint."""
    out = []
    for _, pat in patterns:
        m = pat.search(folded)
        if not m:
            continue
        start, end = max(0, m.start() - width), min(len(text), m.end() + width)
        out.append(("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else ""))
        if len(out) >= limit:
            break
    return out


def score(item, cats, signals, anti, local, gaz, max_chars):
    blob = "%s\n%s" % (item.get("title", ""), item.get("text", ""))
    if max_chars and len(blob) > max_chars:
        blob = blob[:max_chars]
    folded = fold(blob)

    cat_hits = {}
    for cat, patterns in cats.items():
        hits = [term for term, pat in patterns if pat.search(folded)]
        if hits:
            cat_hits[cat] = hits
    signal_hits = [t for t, p in signals if p.search(folded)]
    anti_hits = [t for t, p in anti if p.search(folded)]
    local_hits = [t for t, p in local if p.search(folded)]
    gaz_hits = [t for t, p in gaz if p.search(folded)]

    total = (W_CATEGORY * sum(len(v) for v in cat_hits.values())
             + W_SIGNAL * len(signal_hits)
             + W_LOCAL * (len(local_hits) + len(gaz_hits))
             + W_ANTI * len(anti_hits))

    if not cat_hits:
        bucket, reason = "priority_low", "sin vocabulario de infraestructura"
    elif not (local_hits or gaz_hits):
        bucket, reason = "priority_low", "sin señal local (probablemente nacional o sindicado)"
    elif anti_hits and not signal_hits and total < 6:
        bucket, reason = "priority_low", "dominan las palabras excluyentes: %s" % ", ".join(anti_hits[:3])
    elif signal_hits:
        bucket, reason = "priority_high", "señal de queja + vocabulario de infraestructura"
    else:
        bucket, reason = "priority_medium", "vocabulario de infraestructura, sin queja explícita"

    all_pats = [p for patterns in cats.values() for p in patterns] + signals
    return {
        "article_url": item["article_url"], "article_date": item["article_date"],
        "source_outlet": item["source_outlet"], "title": item["title"],
        "author": item.get("author"), "chars": len(item.get("text", "")),
        "bucket": bucket, "reason": reason, "score": total,
        "categories_hit": cat_hits, "signals": signal_hits,
        "anti": anti_hits, "local": local_hits + gaz_hits,
        "snippets": snippets(blob, folded, all_pats),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("corpus")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-chars", type=int, default=15000,
                    help="max title+body characters to score per article; 0 means full text")
    args = ap.parse_args()

    corpus = json.load(open(args.corpus, encoding="utf-8"))
    cats, signals, anti = load_vocab()
    local = compile_terms(LOCAL_TERMS)
    gaz = gazetteer_terms()

    ranked = [score(item, cats, signals, anti, local, gaz, args.max_chars)
              for item in corpus["items"]]
    ranked.sort(key=lambda r: (-r["score"], r["article_date"]))

    buckets = Counter(r["bucket"] for r in ranked)
    payload = {"corpus": os.path.basename(args.corpus), "window": corpus.get("window"),
               "total": len(ranked), "buckets": dict(buckets),
               "weights": {"category": W_CATEGORY, "signal": W_SIGNAL,
                           "local": W_LOCAL, "anti": W_ANTI},
               "items": ranked}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)

    print("%d articles scored -> %s" % (len(ranked), args.out))
    print("all %d are to be read; the tiers below are reading order only" % len(ranked))
    for name in ("priority_high", "priority_medium", "priority_low"):
        print("  %-15s %5d" % (name, buckets[name]))
    top = Counter()
    for r in ranked:
        top.update(r["categories_hit"].keys())
    print("  categories across the corpus:", dict(top.most_common()))


if __name__ == "__main__":
    main()
