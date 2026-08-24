#!/usr/bin/env python3
"""Colonia Facebook-group intake -> annotated worklist (social layer PoC).

The operator collects public posts from colonia-scoped groups by hand into an
intake file (see --template). This script does only the mechanical part of
locating them, mirroring the repo's split of judgement vs. code:

  * every post inherits its group's colonia as an APPROXIMATE location
    ("the container is the geotag"),
  * the post text is matched against state/gazetteer.json; a street or
    landmark hit upgrades the suggestion to EXACT and carries the snippet
    that will back location_evidence.

It never fetches anything and never decides whether a post qualifies — the
agent reads the worklist and writes data/extract-ugc-<date>.json in the same
schema as news records, with three conventions:

  article_url    = the post URL           source_outlet = "facebook:<group>"
  author         = null (ALWAYS — resident names are never stored)
  plus the extras: source_type "facebook", location_basis
  "gazetteer_match" | "group_scope". For group-scope-only records,
  location_evidence is "grupo de la colonia <X> (<group name>)" — the group's
  name/scope is the evidence, and store.py's honesty check still applies.

Then: python3 store.py data/extract-ugc-<date>.json  (unchanged).
"""

import argparse
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
GAZETTEER = os.path.join(ROOT, "state", "gazetteer.json")

INTAKE_POST_FIELDS = {"post_url", "group", "post_date", "text"}

TEMPLATE = {
    "note": ("Public posts from colonia-scoped Facebook groups, collected by "
             "hand. PRIVACY: paste the problem text only — never the poster's "
             "name, profile link, phone number, or house number. Posts from "
             "members-only groups do not belong here."),
    "collected": "YYYY-MM-DD",
    "groups": {
        "Vecinos de <Colonia>": {"colonia": "<Colonia>", "group_url": ""}
    },
    "posts": [
        {"post_url": "", "group": "Vecinos de <Colonia>",
         "post_date": "YYYY-MM-DD", "text": ""}
    ],
}


def fold(text):
    """Accent-fold and lowercase, one output char per input char, so match
    positions in the folded text map straight back to the original."""
    out = []
    for ch in text:
        decomposed = unicodedata.normalize("NFKD", ch)
        base = next((c for c in decomposed if not unicodedata.combining(c)), ch)
        out.append(base.lower())
    return "".join(out)


def gazetteer_patterns():
    """(kind, key, display, compiled whole-word pattern) for every place."""
    gaz = json.load(open(GAZETTEER, encoding="utf-8"))
    pats = []
    for kind in ("streets", "colonias", "landmarks"):
        for key, entry in gaz.get(kind, {}).items():
            if not key.strip():
                continue
            # keys are already norm()-folded; match them as whole words with
            # flexible whitespace, on the folded post text
            words = [re.escape(w) for w in key.split()]
            pat = re.compile(r"(?<![a-z0-9])" + r"\s+".join(words) + r"(?![a-z0-9])")
            pats.append((kind, key, entry.get("display", key), pat))
    # longest key first so "brisas del pacifico" wins over any shorter overlap
    pats.sort(key=lambda p: -len(p[1]))
    return pats


def snippet(text, start, end, margin=40):
    lo = max(0, start - margin)
    hi = min(len(text), end + margin)
    prefix = "…" if lo > 0 else ""
    suffix = "…" if hi < len(text) else ""
    return prefix + re.sub(r"\s+", " ", text[lo:hi]).strip() + suffix


def match_places(text, patterns):
    """Gazetteer hits in a post, with the original-text phrase and context."""
    folded = fold(text)
    hits = {"streets": [], "colonias": [], "landmarks": []}
    claimed = []          # spans already taken by a longer match
    for kind, key, display, pat in patterns:
        for m in pat.finditer(folded):
            if any(m.start() < e and m.end() > s for s, e in claimed):
                continue
            claimed.append((m.start(), m.end()))
            hits[kind].append({
                "display": display,
                "phrase_in_post": text[m.start():m.end()],
                "snippet": snippet(text, m.start(), m.end()),
            })
            break             # one hit per place per post is enough
    return hits


def check_intake(intake):
    problems = []
    groups = intake.get("groups") or {}
    for name, info in groups.items():
        if not (info or {}).get("colonia"):
            problems.append("group %r has no colonia" % name)
    seen_urls = set()
    for i, post in enumerate(intake.get("posts") or []):
        where = "post %d (%s)" % (i, post.get("post_url") or "no url")
        extra = set(post) - INTAKE_POST_FIELDS
        if extra:
            # the intake must not smuggle in poster identities or ad-hoc fields
            problems.append("%s: unexpected fields %s — intake posts carry "
                            "only %s" % (where, sorted(extra),
                                         sorted(INTAKE_POST_FIELDS)))
        for field in INTAKE_POST_FIELDS:
            if not post.get(field):
                problems.append("%s: missing %s" % (where, field))
        if post.get("group") and post["group"] not in groups:
            problems.append("%s: group %r not declared in groups" % (where, post["group"]))
        if post.get("post_date") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", post["post_date"]):
            problems.append("%s: post_date must be YYYY-MM-DD" % where)
        url = post.get("post_url")
        if url in seen_urls:
            problems.append("%s: duplicate post_url" % where)
        seen_urls.add(url)
    return problems


def build_worklist(intake):
    patterns = gazetteer_patterns()
    groups = intake["groups"]
    items = []
    for post in intake["posts"]:
        group = groups[post["group"]]
        hits = match_places(post["text"], patterns)
        exact = bool(hits["streets"] or hits["landmarks"])
        items.append({
            "post_url": post["post_url"],
            "post_date": post["post_date"],
            "group": post["group"],
            "group_colonia": group["colonia"],
            "text": post["text"],
            "gazetteer_hits": hits,
            "suggested": {
                "location_certainty": "exact" if exact else "approximate",
                "location_basis": "gazetteer_match" if (exact or hits["colonias"])
                                  else "group_scope",
                "colonia": (hits["colonias"][0]["display"] if hits["colonias"]
                            else group["colonia"]),
                "group_scope_evidence": "grupo de la colonia %s (%s)"
                                        % (group["colonia"], post["group"]),
            },
        })
    return items


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("intake", nargs="?", help="data/ugc/intake-<date>.json")
    ap.add_argument("--out", help="worklist output path (default data/ugc-worklist-<date>.json)")
    ap.add_argument("--template", metavar="PATH", help="write a blank intake file and exit")
    args = ap.parse_args()

    if args.template:
        if os.path.exists(args.template):
            sys.exit("refusing to overwrite %s" % args.template)
        os.makedirs(os.path.dirname(os.path.abspath(args.template)), exist_ok=True)
        with open(args.template, "w", encoding="utf-8") as fh:
            json.dump(TEMPLATE, fh, indent=2, ensure_ascii=False)
        print("template written to", args.template)
        return
    if not args.intake:
        ap.error("give an intake file or --template PATH")

    intake = json.load(open(args.intake, encoding="utf-8"))
    problems = check_intake(intake)
    if problems:
        for p in problems:
            print("INTAKE PROBLEM:", p, file=sys.stderr)
        sys.exit(1)

    items = build_worklist(intake)
    out = args.out or os.path.join(DATA, "ugc-worklist-%s.json" % intake["collected"])
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"collected": intake["collected"], "source_type": "facebook",
                   "items": items}, fh, indent=2, ensure_ascii=False)

    located_exact = sum(1 for i in items if i["suggested"]["location_certainty"] == "exact")
    by_basis = {}
    for i in items:
        by_basis[i["suggested"]["location_basis"]] = by_basis.get(i["suggested"]["location_basis"], 0) + 1
    print("worklist written to", out)
    print("%d posts | exact-candidate: %d | basis: %s"
          % (len(items), located_exact, json.dumps(by_basis)))


if __name__ == "__main__":
    main()
