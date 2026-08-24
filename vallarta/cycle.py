#!/usr/bin/env python3
"""LEARN and REPORT phases of the daily cycle.

  python3 cycle.py learn  2026-08-24    # grow gazetteer / vocabulary / sources
  python3 cycle.py report 2026-08-24    # Task 4 daily output

The gazetteer only ever receives place names that came from a record whose
`location_evidence` quoted them, so nothing enters it that the honesty rules
would not already allow.
"""

import json
import os
import re
import sys
from collections import Counter

import store

ROOT = store.ROOT
DATA = store.DATA
STATE = os.path.join(ROOT, "state")
PREFIX = "" if store.CITY == "vallarta" else "%s-" % store.CITY
GAZETTEER = os.path.join(STATE, "%sgazetteer.json" % PREFIX)
VOCAB = os.path.join(STATE, "vocabulary.json")
SOURCES = os.path.join(STATE, "candidate_sources.json")
COVERAGE = os.path.join(STATE, "%scoverage.json" % PREFIX)


def _add(bucket, value, rec):
    if not value:
        return False
    key = store.norm(value)
    entry = bucket.setdefault(key, {"display": value, "seen": 0, "first_seen": rec["article_date"],
                                    "last_seen": rec["article_date"], "evidence_urls": []})
    entry["seen"] += 1
    entry["last_seen"] = max(entry["last_seen"], rec["article_date"])
    if rec["article_url"] not in entry["evidence_urls"]:
        entry["evidence_urls"].append(rec["article_url"])
    return True


def learn(cycle):
    records = store.load(store.RECORDS, [])
    gaz = store.load(GAZETTEER, {"streets": {}, "colonias": {}, "landmarks": {}})
    before = sum(len(gaz[k]) for k in gaz)

    for rec in records:
        # a street field may hold a corner: split it into its parts
        for piece in store.split_street(rec.get("street")):
            _add(gaz["streets"], piece, rec)
        _add(gaz["colonias"], rec.get("colonia"), rec)
        _add(gaz["landmarks"], rec.get("landmark"), rec)

    store.save(GAZETTEER, gaz)
    after = sum(len(gaz[k]) for k in gaz)

    coverage = store.load(COVERAGE, {
        "colonia_master_list": None,
        "colonia_master_list_note": (
            "NOT SET. A full Puerto Vallarta colonia list must be supplied by a human from an "
            "authoritative source (municipal or INEGI). Inventing one would violate the rule "
            "against fabricated place names, so blind-spot analysis stays partial until then."),
        "colonias_heard_from": [],
    })
    heard = sorted({g["display"] for g in gaz["colonias"].values()})
    coverage["colonias_heard_from"] = heard
    coverage["last_updated"] = cycle
    store.save(COVERAGE, coverage)

    print("gazetteer: %d -> %d entries (%d streets, %d colonias, %d landmarks)"
          % (before, after, len(gaz["streets"]), len(gaz["colonias"]), len(gaz["landmarks"])))
    print("colonias heard from: %s" % (", ".join(heard) or "(none)"))


def corpus_progress():
    """Read-so-far vs not-yet-read, for every corpus backfill in flight.

    Operator decision, 2026-08-24: nothing is screened out, so a corpus is not
    finished until every article in it has been read. Until then the report has
    to say so — a qualified count drawn from 12% of a corpus is not a finding
    about the corpus, and presenting it as one would be the exact dishonesty the
    screening rule was abolished to prevent.
    """
    out = []
    for name in sorted(os.listdir(DATA)):
        if not (name.startswith("archive-progress-") and name.endswith(".json")):
            continue
        prog = store.load(os.path.join(DATA, name), {})
        total = prog.get("total_articles") or 0
        done = prog.get("processed_count") or len(prog.get("processed_urls", []))
        if not total:
            continue
        out.append({"corpus": prog.get("corpus", name), "total": total, "read": done,
                    "remaining": total - done, "batches": len(prog.get("batches", [])),
                    "qualified": sum(b.get("qualified", 0) for b in prog.get("batches", [])),
                    "unsure": sum(b.get("unsure", 0) for b in prog.get("batches", []))})
    return out


def report(cycle):
    triage_path = os.path.join(DATA, "%striage-%s.json" % (PREFIX, cycle))
    triage = store.load(triage_path, None)
    records = [r for r in store.load(store.RECORDS, [])]
    incidents = store.load(store.INCIDENTS, [])
    # The triage file may include items from an earlier same-day run. Prefer the
    # extraction file, which is the exact batch passed to store.py, so reruns do
    # not count already-known incidents as newly opened.
    extract_path = os.path.join(DATA, "%sextract-%s.json" % (PREFIX, cycle))
    extracted = store.load(extract_path, None)
    cycle_urls = ({r["article_url"] for r in extracted}
                  if extracted is not None else
                  {d["article_url"] for d in (triage or {"decisions": []})["decisions"]})
    cycle_recs = [r for r in records if r["article_url"] in cycle_urls]

    # Reports are human-facing, so they are written in Spanish (operator
    # decision, 2026-08-24); enum values stay in English everywhere else.
    lines = ["# Informe diario — %s — %s" % (store.CITY, cycle), ""]
    if triage:
        counts = Counter(d["decision"] for d in triage["decisions"])
        decisions = triage["decisions"]
        read = sum(1 for d in decisions if d.get("read_by_agent", True))
        lines += ["## Artículos"]
        if triage.get("reading_note"):
            lines += ["", "> %s" % triage["reading_note"], ""]
        lines += ["- revisados y leídos como texto completo: %d" % read]
        if read != len(decisions):
            # Nothing is screened out any more, so an unread article is a
            # failure to report, not a policy. Name it rather than folding it
            # into the scanned count.
            lines += ["- **triados sin lectura de texto completo: %d** — ver la"
                      " lista de no procesados abajo" % (len(decisions) - read)]
        lines += ["- califican: %d" % counts["yes"],
                  "- dudosos (retenidos para revisión humana): %d" % counts["unsure"],
                  "- leídos pero no son una queja de infraestructura pública: %d" % counts["no"],
                  "- páginas de artículo completas descargadas: %d" % sum(1 for d in decisions if d.get("full_page_fetched")),
                  ""]
    # An article either opened an incident (it is that incident's first article)
    # or was merged into one. Counting records in multi-article incidents instead
    # would call the opening article a merge too.
    first_urls = {i["article_urls"][0] for i in incidents if i.get("article_urls")}
    opened = [r for r in cycle_recs if r["article_url"] in first_urls]
    merged = [r for r in cycle_recs if r["article_url"] not in first_urls]
    lines += ["## Incidentes",
              "- incidentes nuevos abiertos: %d" % len({r.get("incident_id") for r in opened}),
              "- artículos fusionados a un incidente existente: %d" % len(merged),
              "- incidentes en seguimiento en total: %d" % len(incidents),
              ""]
    cert = Counter(r["location_certainty"] for r in cycle_recs)
    total = max(len(cycle_recs), 1)
    cert_label = {"exact": "exacta", "approximate": "aproximada", "none": "sin ubicación"}
    lines += ["## Certeza de ubicación (este ciclo)"]
    for level in ("exact", "approximate", "none"):
        lines.append("- %s: %d (%.0f%%)" % (cert_label[level], cert[level], 100.0 * cert[level] / total))
    located = 100.0 * (cert["exact"] + cert["approximate"]) / total
    lines += ["- **proporción ubicada (exacta+aproximada): %.0f%%**" % located, ""]

    allcert = Counter(r["location_certainty"] for r in records)
    alltotal = max(len(records), 1)
    lines += ["## Certeza de ubicación (todos los ciclos)",
              "- exacta %d / aproximada %d / sin ubicación %d — proporción ubicada %.0f%%"
              % (allcert["exact"], allcert["approximate"], allcert["none"],
                 100.0 * (allcert["exact"] + allcert["approximate"]) / alltotal), ""]

    progress = corpus_progress()
    if progress:
        lines += ["## Backfill del corpus — leído hasta ahora vs pendiente de leer"]
        for p in progress:
            pct = 100.0 * p["read"] / max(p["total"], 1)
            lines += ["- `%s`: **%d de %d leídos (%.1f%%)**, %d pendientes de leer, en %d lotes"
                      % (p["corpus"], p["read"], p["total"], pct, p["remaining"], p["batches"]),
                      "  - de la parte ya leída: %d califican, %d dudosos"
                      % (p["qualified"], p["unsure"])]
        if any(p["remaining"] for p in progress):
            lines += ["",
                      "Estos corpus **no están completamente leídos**. Cada artículo en ellos",
                      "debe leerse — nada se descarta — así que las cifras de arriba describen",
                      "la parte leída hasta ahora y nada más. No son una tasa, no son un total",
                      "y no son evidencia de que la parte no leída no contenga quejas."]
        lines.append("")

    if triage:
        unprocessed = [d for d in triage["decisions"] if d.get("unprocessed")]
        lines += ["## Artículos que no se pudieron procesar"]
        lines += ["- %s — %s" % (d["article_url"], d.get("note", "")) for d in unprocessed] or ["- ninguno"]
        lines.append("")

    out = os.path.join(ROOT, "reports", "%sreport-%s.md" % (PREFIX, cycle))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines))
    print("\nwritten to %s" % out, file=sys.stderr)


if __name__ == "__main__":
    cmd, cyc = sys.argv[1], sys.argv[2]
    {"learn": learn, "report": report}[cmd](cyc)
