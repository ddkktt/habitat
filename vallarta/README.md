# Puerto Vallarta infrastructure & well-being map

The goal is a colonia-by-colonia picture of how Puerto Vallarta is doing: what
infrastructure is failing where, how long it has been failing, how many people
it touches, and which parts of the city are never heard from at all. Issues are
**crowdsourced** from public signals, **localized** to streets and colonias only
when the source itself names the place, **contextualized** with duration, scale,
and repeat coverage (a story the press keeps returning to is a signal of public
pressure), and **visualized** on a local dashboard where silence shows up as a
coverage gap rather than good news.

Today the crowd speaks through local news: potholes, water outages, flooded
streets, and dead streetlights reported by the city's outlets, read daily. News
goes first because it is the highest-precision source — it seeds the place
gazetteer, the complaint vocabulary, and the incident model that noisier
sources will be held against. Social media is the next layer: residents'
Facebook groups and official accounts already surface in
`state/candidate_sources.json` as articles mention them, queued for human
approval before anything is read.

The pipeline is run by an AI agent working to `../vallarta_agent_prompt.md`,
and the design splits the work deliberately:

- **Judgement stays with the agent** — deciding whether an article qualifies,
  extracting the record, flagging its own doubts. These calls are made against
  the article text, never automated away.
- **The non-negotiables live in code** — rate limits, fetch-once, the
  no-evidence-no-location rule, privacy, incident merging. Scripts enforce what
  must never be improvised, so an agent having a bad day cannot bend them.

The loop is recursive, not just repetitive: every cycle ends by mining its own
output — new streets and colonias join a gazetteer, new vocabulary joins the
watch list, mentioned outlets become candidate sources for human approval — and
each changelog entry starts by measuring whether the previous cycle's changes
actually helped, reverting the ones that didn't.

**Read-only by rule**: it fetches public feeds and article pages, honors
robots.txt, waits 5 seconds between requests, never fetches a URL twice, and
never posts, submits, or contacts anyone. It stores extracted facts plus one
short evidence quote per record — never article text.

## Run one cycle

```bash
python3 feeds.py                       # COLLECT: read the four feeds -> data/worklist-<date>.json
#                                        (then read the worklist, triage it, and write
#                                         data/extract-<date>.json and data/triage-<date>.json)
python3 store.py data/extract-<date>.json   # EXTRACT+VERIFY: validate, dedupe, merge incidents
python3 cycle.py learn  <date>         # LEARN:  grow gazetteer / coverage state
python3 cycle.py report <date>         # REPORT: Task 4 daily output -> reports/report-<date>.md
```

## Social layer (PoC): colonia Facebook groups

Posts from colonia-scoped groups are semi-geolocated by construction — the
group *is* the geotag (`approximate`), and a gazetteer hit in the post text
upgrades the record to `exact`. Intake is manual and read-only: the operator
copies public posts by hand (problem text only — never poster names, profiles,
or house numbers; members-only groups are out of scope), so nothing is scraped
and no platform ToS is touched.

```bash
python3 ugc.py --template data/ugc/intake-<date>.json   # blank intake to fill by hand
python3 ugc.py data/ugc/intake-<date>.json              # locate -> data/ugc-worklist-<date>.json
#   (then read the worklist, triage it — same judgement rules as news — and
#    write data/extract-ugc-<date>.json; agent conventions in ugc.py's docstring)
python3 store.py data/extract-ugc-<date>.json           # unchanged: validate, dedupe, merge
```

Social records carry `source_type: "facebook"` and `location_basis:
"gazetteer_match" | "group_scope"`, and merge into the same incidents as press
records — a complaint heard in both channels raises `coverage_count`, and one
heard only on social marks a press blind spot.

## Backfill and audits

```bash
python3 archive.py --after <date> --before <date>   # backfill corpus from public archives
python3 prefilter.py data/corpus.json --out data/ranked.json   # set the reading order
python3 readqueue.py status                         # read so far vs not yet read
python3 readqueue.py next --n 25 --label b051       # next articles, full text, in reading order
python3 batchlog.py --batch <id> --triage <file> --extract <file>   # log a finished batch
python3 readqueue.py audit                          # reconcile progress against the triage files
python3 sample.py records --n 10                    # weekly quality check (target: 90% accuracy)
```

The archive backfill (human-authorised, see `CHANGELOG.md`) uses each outlet's
bulk endpoints where robots.txt allows them — far gentler than page-by-page
fetching.

**Every article in a corpus is read.** Operator decision, 2026-08-24: the
screening rule is abolished. `prefilter.py` still scores each article, but the
score now sets only the *order* in which articles are read — `priority_low`
means "read this last", never "skip this". Nothing is `screened_out`, no verdict
is reached from a headline when the text is available, and `sample.py screened`
(which sampled the discarded pile to see what the filter was swallowing) is
retired, because there is no discarded pile left to sample.

Two consequences worth knowing:

- A corpus read is not finished until every article in it is read, so reports
  and the dashboard separate **read so far** from **not yet read**. A qualified
  count drawn from part of a corpus describes that part and nothing else.
- `readqueue.py audit` reconciles the progress file against the triage files.
  The progress file is a summary; the triage files are the evidence, and a read
  that left no decision row behind is not a read. Run it after any fan-out of
  batches.

## Two cities

`state/sources.json` holds one feed set per city. Everything is keyed off
`MAPPER_CITY`, which defaults to `vallarta`:

```bash
python3 feeds.py                                   # Puerto Vallarta
MAPPER_CITY=gdl python3 feeds.py                   # Guadalajara / ZMG
MAPPER_CITY=gdl python3 cycle.py report 2026-08-24
MAPPER_CITY=gdl python3 server.py --port 8001      # its own dashboard
```

Records, incidents, gazetteers and reports are stored per city, so one city's
numbers never enter the other's metrics.

## Visualize it

```bash
python3 server.py                 # opens http://localhost:8000
python3 server.py --port 9000 --no-browser
```

A dashboard centred on a live city map: incidents per colonia drawn with
Leaflet over OpenStreetMap tiles, filterable by category, status and month
(with a play button that walks through the months), and clickable through to
each colonia's incidents. Below it: incidents with their evidence quote and
source links, per-cycle counts and exclusion reasons, and what the agent has
learned so far (gazetteer, vocabulary watch list, candidate sources, coverage
gaps). The server reads `data/` and `state/` on every request, so it shows the
latest cycle with no rebuild — press **Reload** after running a cycle. It is a
viewer only and never touches the news sites; the map layer needs internet for
the tile CDN, and everything else works offline. Marker positions come from
`state/colonia_coords.json` — hand-estimated colonia centres, viewer-only, never
part of any record; a colonia without coordinates is listed beside the map
rather than guessed.

## Where it's headed

- **More voices.** Approved social sources — neighborhood Facebook groups,
  official service accounts — join the feed set in `state/sources.json` under
  the same rules: evidence-quoted locations, no private individuals named,
  read-only. `state/candidate_sources.json` is the on-ramp; a human approves
  each source before it is ever read.
- **Well-being, not just failure.** Resolved repairs, failed repairs, and
  per-colonia silence are already tracked; the aim is a picture of each
  neighborhood's condition over time, not just a complaint log.
- **A real map.** The dashboard grows from lists into a colonia map: incident
  density, duration, and the zones nobody reports on.

## Layout

Python 3, standard library only, no dependencies.

| path | what it holds |
| --- | --- |
| `feeds.py` | polite fetcher; enforces 2 feed reads/day, 1 fetch per article ever, 5s between requests |
| `archive.py` | archive backfill via bulk endpoints, access method chosen per host from robots.txt |
| `prefilter.py` | scores a large corpus into reading-order tiers; decides neither what is read nor what qualifies |
| `readqueue.py` | the full-corpus reading queue: `status`, `next` (full text, in order), `audit` |
| `batchlog.py` | logs a finished batch to the progress file under a lock; rejects verdicts outside the enum |
| `sample.py` | the weekly record re-read (the screened-pile audit is retired) |
| `store.py` | record validation (honesty rule 1 is enforced in code), duplicate detection, incident merge |
| `cycle.py` | LEARN and REPORT phases |
| `server.py` + `web/` | local dashboard; serves the dataset at `/api/data` |
| `cache/ledger.json` | the fetch ledger — **do not delete**, it is what makes "never re-fetch" true across runs |
| `cache/pages/` | one JSON per fetched article: extracted text, byline, date |
| `data/worklist-*.json` | feed items seen that day |
| `data/triage-*.json` | qualify / unsure / exclude decision and reason for every scanned article |
| `data/extract-*.json` | that cycle's extracted records, before ingestion |
| `data/records.json` | every accepted record, one per article |
| `data/incidents.json` | deduplicated real-world incidents with `coverage_count` |
| `state/gazetteer.json` | evidence-backed streets, colonias, landmarks — grows each cycle |
| `state/vocabulary.json` | keyword hints, watch list, anti-keywords |
| `state/candidate_sources.json` | outlets/agencies seen, pending human approval; none are read |
| `state/coverage.json` | which colonias have been heard from, and the missing master list |
| `state/colonia_coords.json` | hand-estimated colonia centres for the dashboard map — viewer aid only, never enters records |
| `reports/` | daily Task 4 reports |
| `EXTRACTION.md` | **how to turn an article into a record — read this before extracting** |
| `CHANGELOG.md` | what each cycle learned and changed, opening with whether the last change helped |

## Honesty by construction

Uncertainty is a valid answer here: a record with honest nulls is worth more
than a record with guesses. The code rejects anything that violates that:

- A `street`, `colonia` or `landmark` is rejected unless its words appear in
  `location_evidence`. No evidence, no location.
- `location_certainty: "none"` may not carry a place value.
- Records with no location never auto-merge into an incident.
- Summaries over 25 words, unknown categories, and unknown statuses are rejected.

Private individuals are never named — complaints matter, complainers' identities
do not. Repeated coverage of the same incident is preserved as `coverage_count`,
because a story the press keeps returning to is a signal of public pressure.
