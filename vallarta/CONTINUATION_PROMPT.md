# Continuation prompt — finish the full read, then widen the net

You are continuing the Puerto Vallarta civic-complaints extraction in
`/Users/ddk/habitat/vallarta`. Read `../vallarta_agent_prompt.md` (governing —
it wins every conflict) and `EXTRACTION.md` (how to apply it) completely before
touching an article. The operator's standing orders, decided 2026-08-24:

- **Everything gets read.** No screening, no headline verdicts, nothing
  `screened_out`. Priority scores order the queue; they never decide whether.
- **Honesty is untouchable.** The triage files record what was actually read.
  An unreadable stub gets `decision: "unprocessed"` + `read_by_agent: false` —
  never a verdict faked from its headline. Anything restored from a transcript
  carries `restored_from_transcript` provenance. Reports separate read-so-far
  from not-yet-read until a corpus is genuinely finished, then say so outright.
- Privacy, read-only, and rate-limit rules are unchanged and not yours to
  change. New sources go to `state/candidate_sources.json` for operator
  approval; only approved sources are fetched.

## Phase 0 — Situational awareness (do this before any work)

1. `python3 readqueue.py status` and `python3 readqueue.py audit` — the audit
   must be clean before and after anything you do; run it between batches, not
   only at the end.
2. `ListAgents` + check whether a full-read workflow or peer session is already
   working. Coordination lives over SendMessage. Do not assume a lane is free —
   **verify claims against what is on disk** (this rule was earned twice today).
3. Check `CHANGELOG.md` top entries — they are the operational history of the
   full read, including every failure mode listed at the bottom of this prompt.

## Phase 1 — Finish `corpus-pv` (7,665 articles)

Remaining work is whatever `readqueue.py status` says is unread. Pre-assigned
batch files live in `data/fullread-batches/` (b101–b211); if a batch's articles
are partly done, filter against `processed_urls` — but **never conclude
"nothing to read" from that file alone**: it is a summary; the triage files are
the evidence. If assignments are exhausted or stale, cut makeup batches with
the workflow **generation in both filename and batch id** (e.g.
`triage-archive-full-g3-2026-08-24-bNNN.json`, batch id
`archive-full-g3-2026-08-24-bNNN`) so two generations physically cannot
overwrite each other.

Per batch: read every article's full text → triage decision (`yes`/`unsure`/
`no`/`unprocessed`, reason codes in EXTRACTION.md §2; `out_of_area` only for a
real complaint outside the municipality — non-complaints get their topic code)
→ records for yes/unsure per §3–§4 (one evidence quote max; no evidence, no
place; municipality-wide = certainty `none`; summary ≤25 English words; never a
private individual's name) → `python3 store.py <extract>` (flock-serialized;
fix rejections per §6, fix the record not the check) → `python3 batchlog.py
--batch <id> --triage <file> --extract <file>` (flock-serialized, validates
verdicts, refuses empty batches — if it refuses, the triage file is wrong, fix
it, never force).

Closing the corpus requires: audit clean; every one of the 42 near-empty stubs
accounted for as `unprocessed` (publish the closing count); any triage file
whose decision count is below its logged `scanned` restored from workflow
transcripts (in `~/.claude/projects/*/subagents/workflows/wf_*/agent-*.jsonl` —
the agents' generator scripts embed their verdicts) with provenance marked;
then `cycle.py learn`, `cycle.py report`, `sample.py records --n 10` (below 90%
accuracy: stop and report), and a changelog entry that states the corpus read
is COMPLETE so the partial-corpus caveat is retired, and records anything you
changed and anything you propose but may not change.

## Phase 2 — Finish `corpus-diario` (667 articles, ~357 still untriaged)

Same rules, smaller corpus. It has **no progress ledger yet** — create
`data/archive-progress-diario-<date>.json` in the same shape (or extend
batchlog with a `--progress` flag) rather than logging Diario batches into the
pv ledger. Cross-check against existing triage files first: ~310 of its
articles were already triaged during feed cycles; do not re-read those, and do
not trust any single summary file over the triage evidence.

## Phase 3 — Amplify the search (in priority order)

1. **NoticiasPV archive backfill.** Approved source; the highest complaint
   density of any feed (50% on day one). Its WordPress REST endpoint
   (`/wp-json/wp/v2/posts`) was confirmed working at approval time. Build
   `corpus-noticiaspv.json` with `archive.py`-style pagination — respect the
   rate rules (5s between requests, fetch-once, cache raw pages), then full-read
   it like Phase 1. Expect a high record yield; this is the single most
   valuable expansion.
2. **Meridiano + Banderas News archives.** Both approved 2026-08-24. Probe
   REST/sitemap availability first (read-only, log the recon in
   `state/source_recon-<date>.json`). Meridiano: only Bahía de Banderas
   coverage is in scope — filter by `local_terms`, and expect low yield; if an
   archive pull yields ~nothing qualifying, record that and propose demotion
   rather than silently keeping it.
3. **Daily feeds continue** for all six approved sources — the twice-per-day
   cap and the normal cycle are unchanged by any of this.
4. **Source recon round 2** (candidates only — nothing fetched regularly
   without operator approval): re-probe Reporte Diario and Vallarta Opina via
   sitemap.xml (both lacked RSS; Opina also has broken TLS — do not disable
   certificate verification for a recurring source without operator sign-off);
   re-check La Noticia al Punto for recovery from its casino-spam compromise
   before ever trusting it; probe an official-notices channel for SEAPAL
   (their site had none — check for a Telegram/X presence and log it as a
   candidate). Log every finding in `state/candidate_sources.json` with a
   recon verdict and leave approval to the operator.
5. **Keyword backfill.** `keyword_backfill.py` exists — with the corpus fully
   read it is no longer needed for pv, but run it against any NEW corpus you
   build whose full read hasn't happened yet, purely as reading-order.

## Failure modes already paid for (do not repeat them)

- Two workflow generations sharing filenames destroyed 300 verdicts (restored
  from transcripts). Generation-scoped names prevent the class.
- A killed workflow's in-flight agents survive as zombies and keep writing.
  After any workflow stop, sweep for late writes before relaunching.
- Agents given "follow the docs" + a doc describing a different workflow will
  follow the doc: state precedence explicitly (docs govern judgement, your
  prompt governs mechanics). `readqueue.py next` is single-reader ONLY — its
  claims race under fan-out.
- `processed_urls` without a triage row is not a read. A batch with zero
  decisions is never logged. An empty-looking situation is checked against the
  triage files before any conclusion.
- Multi-writer JSON needs the flocks that exist (`batchlog.py`, `.store.lock`).
  Never hand-edit `archive-progress*.json`.
- Unrecognized verdict strings get silently counted as exclusions by
  consumers; `batchlog.py` validates, but write `yes`/`unsure`/`no`/
  `unprocessed` exactly.
- Peers' claims and your own assumptions are checked against the artifact on
  disk before acting. Both directions of that lesson were paid for today.

Scale note: a multi-agent workflow at fan-out needs the operator's explicit
go-ahead in their own words each time. Sequential work in one session needs no
approval. The full-read mandate is standing; the token spend to parallelize it
is not.
