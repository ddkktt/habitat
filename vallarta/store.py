#!/usr/bin/env python3
"""Record store, duplicate detection and incident merging (Task 3).

An *article record* is one extraction from one article. An *incident* is a
real-world problem that one or more articles cover. Two articles are the same
incident when they match on category AND location AND overlap in time within a
14-day window (the rule from vallarta_agent_prompt.md).

Nothing here guesses: matching uses only the place names already recorded, which
in turn only exist when `location_evidence` quoted them.
"""

import json
import os
import re
import unicodedata
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
# One dataset per city. MAPPER_CITY=gdl keeps Guadalajara records out of the
# Puerto Vallarta store, so neither city's numbers contaminate the other's.
CITY = os.environ.get("MAPPER_CITY", "vallarta")
_suffix = "" if CITY == "vallarta" else "-%s" % CITY
RECORDS = os.path.join(DATA, "records%s.json" % _suffix)
INCIDENTS = os.path.join(DATA, "incidents%s.json" % _suffix)

DUP_WINDOW_DAYS = 14

REQUIRED = ["article_url", "article_date", "source_outlet", "author", "qualifies",
            "categories", "status", "location_certainty", "location_evidence",
            "street", "colonia", "landmark", "summary",
            "affected_people_clue", "duration_clue"]

CATEGORIES = {"roads", "water", "drainage", "flooding", "lighting", "power",
              "trash", "public_space", "transit", "other"}
STATUSES = {"new_complaint", "ongoing", "failed_repair", "resolved", "unclear"}
CERTAINTY = {"exact", "approximate", "none"}


def norm(text):
    """Fold case and accents so 'Brisas del Pacífico' == 'brisas del pacifico'."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Drop generic place nouns and connectors so "vertederos de Laureles" and
    # "Laureles" fingerprint the same. Names, not street furniture, do the matching.
    text = re.sub(r"\b(avenida|av|calle|c|blvd|bulevar|colonia|col|fracc|fraccionamiento"
                  r"|vertedero|vertederos|centro|cultural|parque|plaza|mercado|escuela"
                  r"|colegio|hotel|iglesia|puente|glorieta|retorno|privada"
                  r"|de|del|la|el|los|las)\b\.?", " ", text.lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text)).strip()


def load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return default


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def validate(rec):
    """Return a list of problems. Honesty rule 1 is enforced here, not trusted."""
    problems = []
    for field in REQUIRED:
        if field not in rec:
            problems.append("missing field: %s" % field)
    if problems:
        return problems
    if rec["qualifies"] not in {"yes", "unsure"}:
        problems.append("qualifies must be yes|unsure")
    if rec["status"] not in STATUSES:
        problems.append("bad status: %s" % rec["status"])
    if rec["location_certainty"] not in CERTAINTY:
        problems.append("bad location_certainty: %s" % rec["location_certainty"])
    for cat in rec["categories"]:
        if cat not in CATEGORIES:
            problems.append("bad category: %s" % cat)
    if rec.get("same_incident_as") and not isinstance(rec["same_incident_as"], str):
        problems.append("same_incident_as must be an article_url string")
    if len(rec["summary"].split()) > 25:
        problems.append("summary over 25 words (%d)" % len(rec["summary"].split()))

    # Honesty rule 1: no place value may exist without evidence words backing it.
    ev = norm(rec.get("location_evidence"))
    for field in ("street", "colonia", "landmark"):
        value = rec.get(field)
        if not value:
            continue
        if not ev:
            problems.append("%s set but location_evidence is null" % field)
            continue
        tokens = [t for t in norm(value).split() if len(t) > 2]
        if tokens and not any(t in ev for t in tokens):
            problems.append("%s=%r is not supported by location_evidence" % (field, value))
    if rec["location_certainty"] == "none" and any(rec.get(f) for f in ("street", "colonia", "landmark")):
        problems.append("location_certainty 'none' but a place field is filled")
    if rec["location_certainty"] != "none" and not rec.get("location_evidence"):
        problems.append("location_certainty %r without evidence" % rec["location_certainty"])
    return problems


def split_places(value):
    """'Av. Francisco Villa esquina calle Viena' -> both street names.

    A corner names two streets. Keeping them joined would stop a later article
    that mentions only one of them from matching the same incident.
    """
    return [p.strip() for p in re.split(r"\s+(?:esquina|esq\.?|y)\s+", value or "") if p.strip()]


split_street = split_places   # kept: cycle.py and older callers use this name


def place_key(rec):
    """The location fingerprint used for duplicate matching."""
    parts = [norm(rec.get("colonia"))]
    parts += [norm(p) for p in split_places(rec.get("landmark"))]
    parts += [norm(p) for p in split_places(rec.get("street"))]
    return tuple(dict.fromkeys(p for p in parts if p))


def same_incident(rec, inc):
    """Category AND location AND time overlap, per Task 3."""
    if not set(rec["categories"]) & set(inc["categories"]):
        return False
    rec_places, inc_places = set(place_key(rec)), set(inc.get("place_key", []))
    if not rec_places or not inc_places:
        return False                      # unlocated records never auto-merge
    if not rec_places & inc_places:
        return False
    try:
        d1 = datetime.strptime(rec["article_date"], "%Y-%m-%d").date()
        d2 = datetime.strptime(inc["last_article_date"], "%Y-%m-%d").date()
    except ValueError:
        return False
    return abs((d1 - d2).days) <= DUP_WINDOW_DAYS


def ingest(new_records):
    """Add records, merging into existing incidents where Task 3 says to.

    Returns a summary dict for the daily report.
    """
    records = load(RECORDS, [])
    incidents = load(INCIDENTS, [])
    known = {r["article_url"] for r in records}

    added, merged, skipped, rejected = [], [], [], []
    for rec in new_records:
        problems = validate(rec)
        if problems:
            rejected.append({"article_url": rec.get("article_url"), "problems": problems})
            continue
        if rec["article_url"] in known:
            skipped.append(rec["article_url"])
            continue

        # An explicit link is a judgement the agent states and signs for, unlike
        # place matching which is mechanical. Needed for events with no location:
        # those never auto-merge, by design, so identical coverage would otherwise
        # split into separate incidents.
        hint = rec.get("same_incident_as")
        target = None
        if hint:
            target = next((i for i in incidents if hint in i["article_urls"]), None)
            if target is None:
                rejected.append({"article_url": rec.get("article_url"),
                                 "problems": ["same_incident_as points at an unknown article: %s" % hint]})
                continue
        if target is None:
            target = next((i for i in incidents if same_incident(rec, i)), None)
        if target:
            target["article_urls"].append(rec["article_url"])
            target["coverage_count"] = len(target["article_urls"])
            target["last_article_date"] = max(target["last_article_date"], rec["article_date"])
            if rec["status"] != "unclear" and rec["status"] != target["status"]:
                target.setdefault("status_history", []).append(
                    {"date": rec["article_date"], "from": target["status"], "to": rec["status"]})
                target["status"] = rec["status"]
            target["categories"] = sorted(set(target["categories"]) | set(rec["categories"]))
            rec["incident_id"] = target["incident_id"]
            if hint:
                target.setdefault("linked_by_agent", []).append(rec["article_url"])
            merged.append((rec["article_url"], target["incident_id"]))
        else:
            incident_id = "INC-%s-%03d" % (rec["article_date"].replace("-", ""), len(incidents) + 1)
            incidents.append({
                "incident_id": incident_id,
                "categories": sorted(set(rec["categories"])),
                "status": rec["status"],
                "colonia": rec["colonia"],
                "street": rec["street"],
                "landmark": rec["landmark"],
                "place_key": list(place_key(rec)),
                "first_article_date": rec["article_date"],
                "last_article_date": rec["article_date"],
                "article_urls": [rec["article_url"]],
                "coverage_count": 1,
                "summary": rec["summary"],
            })
            rec["incident_id"] = incident_id
            added.append(incident_id)
        records.append(rec)
        known.add(rec["article_url"])

    save(RECORDS, records)
    save(INCIDENTS, incidents)
    return {"new_incidents": added, "merged": merged,
            "already_known": skipped, "rejected": rejected,
            "total_records": len(records), "total_incidents": len(incidents)}


if __name__ == "__main__":
    import fcntl
    import sys
    incoming = json.load(open(sys.argv[1], encoding="utf-8"))
    # Two sessions ingest in parallel during the full-corpus read; records.json
    # and incidents.json are read-modify-write, so serialize the whole ingest.
    with open(os.path.join(DATA, ".store.lock"), "w") as _lock:
        fcntl.flock(_lock, fcntl.LOCK_EX)
        print(json.dumps(ingest(incoming), indent=2, ensure_ascii=False))
