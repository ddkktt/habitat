# Extraction reference

How to turn an article into a record. Written for whoever runs the next cycle —
the judgement calls in here were learned by making them, and several were learned
by getting them wrong first.

The governing document is `../vallarta_agent_prompt.md`. Where this file and that
one disagree, that one wins. This file only says how to apply it.

---

## 1. The three questions, in order

**Does it qualify?** An article qualifies if it describes a *problem with public
infrastructure or services affecting residents*: roads and potholes, water supply,
leaks, drainage and sewage, flooding, street lighting, power, rubbish collection,
public spaces and green areas, sidewalks, bridges, public transit conditions.

Excluded even when the article says "denuncia": crime, political accusations,
medical complaints, labour disputes, accusations against individuals.

Three answers are allowed, and `unsure` is a real answer, not a hedge:

| Verdict | When |
| --- | --- |
| `yes` | A public-infrastructure problem affecting residents is described. |
| `unsure` | Genuinely borderline. Record it and say why in the summary. |
| *(no record)* | Not a complaint. Log the reason in the triage file; never delete. |

**Where is it?** See §3. The default answer is `none`, and `none` is not a failure.

**Is it already an incident?** See §5 before saving.

---

## 2. Reason codes for exclusions

Every scanned article gets a decision in `data/triage-<cycle>.json`, including the
ones you exclude. Exclusions are data: a mis-triaged topic shows up as a pattern
in the Ciclos tab instead of vanishing.

| Code | Meaning |
| --- | --- |
| `qualified` | Recorded, `qualifies: yes` |
| `unsure` | Recorded, `qualifies: unsure` |
| `off_topic_crime` | Homicide, arrests, cartel, police operations |
| `off_topic_politics` | Party politics, appointments, legislative process |
| `off_topic_other` | Sport, weather forecasts, culture, business, national wire |
| `event_not_complaint` | Clean-up drives, festivals, awareness campaigns |
| `official_statement_no_problem` | An authority reporting progress or normal operation |
| `out_of_area` | A real complaint, but outside the municipality |
| `headline_not_infrastructure` | Judged from the headline alone (say so — see §7) |

Add a new code rather than forcing a bad fit, and note it in the changelog.

---

## 3. Location — the part that goes wrong

### The one rule everything else serves

**No evidence, no location.** `street`, `colonia` and `landmark` may only be
filled if `location_evidence` contains the article's own words naming that place.
If you cannot quote it, the value is `null`. Never infer a colonia from knowing
the city. `store.py` enforces this mechanically; see §6.

### Choosing the certainty level

| Level | Use when | Example |
| --- | --- | --- |
| `exact` | A street, corner, or a colonia plus a specific point is named | "avenida Francisco Villa, en el cruce con la calle Viena" |
| `approximate` | A named area or facility, but no specific point | "los vertederos de Laureles y Coyula-Matatlán" |
| `none` | Only the municipality, or nothing | "cientos de habitantes" without a place |

**Municipality-wide problems are `none`.** A city-wide water crisis names no place
*within* the city. This convention is applied consistently to both the Puerto
Vallarta water crisis and the AMG water-quality complaint. It understates what is
known and depresses the located-share metric — a `municipality` level has been
proposed to the operator, and until they rule, `none` is correct.

### Quoting evidence

The source rules cap you at **one short quoted phrase per record**. That single
quote has to carry every place value you fill in.

- Prefer one contiguous phrase that names everything at once.
- An **ellipsis elision** inside that one quote is allowed: `"Vecinos de la colonia
  Brisas del Pacífico denunciaron … una fuga de agua entre las calles Alemania y
  avenida Víctor Iturbe"`. This is one quotation with a cut, not two quotations.
- A headline is published article text and may be quoted.
- **If a place needs a second, separate quote, drop the place — not the rule.**
  The Brisas del Pacífico leak reached the "centro cultural La Lija"; that sat in
  another sentence, so `landmark` is `null` and the fact is not in the dataset.
  Record the loss in the changelog rather than stretching the quote.

### Compound values

Write a corner as it appears — `"Avenida Francisco Villa esquina calle Viena"`.
`store.split_places()` breaks it apart for matching, so both streets fingerprint
separately. The same applies to landmarks joined by "y".

---

## 4. The remaining fields

**`author`** — the byline as printed, else `null`. A newsroom byline
("Redacción Vallarta Independiente") is fine. This is the *only* personal name
allowed anywhere in a record.

> **Privacy, absolute:** never record the name of a private individual. If the
> article names the resident who complained, omit it. Complaints matter;
> complainers' identities do not.

**`categories`** — one or more of `roads water drainage flooding lighting power
trash public_space transit other`. Note the enum has no `sidewalks`: a broken
sidewalk goes to `public_space`, and an uncovered manhole in one goes to
`drainage`. Multiple categories are normal — the Tonalá storm record carries
`flooding`, `drainage` and `trash` because rubbish blocked the storm drains.

**`status`**

| Value | Use when |
| --- | --- |
| `new_complaint` | First report; no prior notification or repair mentioned |
| `ongoing` | The text says it persists ("se mantiene", "desde hace días") |
| `failed_repair` | It was repaired or attended and failed again |
| `resolved` | The article says it is fixed |
| `unclear` | The text does not say — a valid answer |

**`summary`** — one sentence, **25 words maximum**, in English. If the article is
ambiguous, say so *in the summary* rather than smoothing it over: *"…it is
political commentary, so qualification is doubtful."* If one article covers many
places, say how many (see §7).

**`affected_people_clue` / `duration_clue`** — short phrases from the article
("cientos de habitantes", "más de cuatro días"), else `null`. Keep them to a few
words; they are clues, not quotations.

---

## 5. Duplicates and incidents

Compare against records from the previous **14 days**. Two articles are the same
incident when they match on **category AND location AND overlapping time**. On a
match: do not create an incident, link the article, update the status if it
changed, and let `coverage_count` rise. Repeated coverage is public pressure —
preserve it.

Matching is mechanical and deliberately conservative: **records with no location
never auto-merge.** That is a safety property, not a bug. A false merge destroys
two real incidents; a missed merge only splits one.

When you *know* two unlocated articles cover one event, say so explicitly:

```json
"same_incident_as": "https://…/the-first-article-you-recorded"
```

Four outlets covered one water march that way, giving `coverage_count: 4`. The
link is your stated judgement — it is stored as `linked_by_agent` on the incident,
and is never inferred by the code. Point it at an article already in the store.

---

## 6. What the validator rejects, and what to do

`python3 store.py data/extract-<cycle>.json` refuses bad records before they land.
A rejection is usually correct — fix the record, not the check.

| Message | Meaning | Fix |
| --- | --- | --- |
| `X is not supported by location_evidence` | You filled a place the quote does not name | Requote to cover it, or set the place to `null` |
| `X set but location_evidence is null` | A place with no evidence at all | Set the place to `null` |
| `location_certainty 'none' but a place field is filled` | Contradiction | Raise the certainty or clear the place |
| `location_certainty 'exact' without evidence` | Certainty claimed with nothing behind it | Add the quote or drop to `none` |
| `summary over 25 words (N)` | Too long | Cut it |
| `bad category` / `bad status` | Outside the enum | Use a listed value |
| `same_incident_as points at an unknown article` | Link target not in the store | Ingest that article first |

On the first run of cycle 1 this rejected two of three records, both mine, both
correctly. That is the check working.

---

## 7. Known traps

**One record per article cannot hold several places.** A UDG TV article located
storm flooding at *seven* crossings and colonias; the schema permits one. Record
the worst point, state the count in the summary ("Storm flooded seven points
across Tonalá…"), and know that the other six are not in the dataset. A
`sub_locations` array is proposed and awaiting a human decision.

**Feed text may be truncated.** Some outlets put the full body in the RSS; others
publish an excerpt. If you extract from an excerpt, mark it in the triage file as
`extraction_source: "rss_excerpt"` so nobody later mistakes a thin record for a
thorough one.

**Some pages will not parse.** The El Informador extractor returns a sidebar
headline instead of the article body. Since a page may be fetched only once ever,
raw HTML is now kept in `cache/pages-raw/` so parsing can be redone offline —
but pages fetched before that fix cannot be recovered without human authorisation
to re-fetch.

**Every article gets read. No screening.** Operator decision, 2026-08-24: the
corpus is read in full — all of it, at corpus scale. The prefilter may still
order the reading queue, but nothing is ever `screened_out`, and no verdict is
made from a headline when the text is available (it always is: the corpus
carries full text locally). The old sampling audit of a screened-out pile is
obsolete once no pile exists.

**Do not claim a reading you did not do.** The triage file records, for every
article, that its text was read. Until the full-corpus read completes, the
report separates *read so far* from *not yet read* — never call an unread
article processed. Keep it honest.

---

## 8. Working a cycle

```bash
python3 feeds.py                              # COLLECT  -> data/worklist-<date>.json
python3 prefilter.py <corpus> --out <ranked>  # set the READING ORDER for an archive corpus
#   read, decide, and write:
#     data/extract-<date>.json   the records
#     data/triage-<date>.json    a decision for every article scanned
python3 store.py data/extract-<date>.json     # VALIDATE + merge incidents
python3 cycle.py learn  <date>                # LEARN   gazetteer, coverage
python3 cycle.py report <date>                # REPORT  -> reports/report-<date>.md
python3 sample.py records --n 10              # weekly check; below 90% accuracy, stop
# (sample.py screened is retired: nothing is screened out any more — everything is read)
```

Working a corpus backfill, where the corpus is too large for one sitting:

```bash
python3 readqueue.py status                   # read so far vs not yet read
python3 readqueue.py next --n 25 --label b051 # next 25 in reading order, full text inline
#   read every one of them, then write the triage and extract files
python3 store.py data/extract-archive-<...>.json
python3 batchlog.py --batch <id> --triage <triage> --extract <extract>
python3 readqueue.py audit                    # progress file vs triage files — run between batches
```

> **`readqueue.py next` is for a single reader working interactively.** It hands
> out whatever is unclaimed at the instant it runs, and a claim only becomes
> visible to anyone else once the batch is logged. Several readers calling it at
> once will be handed overlapping work. When work is split across concurrent
> readers, cut the assignments up front into fixed batch files and give each
> reader its own — do not let them draw from the queue. This is the same hazard
> `batchlog.py`'s lock exists for, one layer up.

**Never conclude "nothing to read" from `processed_urls`.** It is a summary; the
triage files are the evidence. A URL can sit in `processed_urls` with no decision
behind it, and if you take that as a read and log an empty batch, the article
stays marked processed, the queue skips it forever, and no verdict exists
anywhere. Four batches did this and stranded 238 articles. `batchlog.py` now
refuses a batch with no decisions; if your assigned articles look already-done,
run `readqueue.py audit` and requeue them rather than logging nothing.

`batchlog.py` takes a lock, so several readers can work one corpus at once. It
refuses a batch whose decisions fall outside `yes`/`unsure`/`no`, or that do not
record whether each article was read: an unrecognised verdict is counted as an
exclusion by everything downstream, which once buried 14 real complaints.

`readqueue.py audit` exists because the progress file is a summary and the
triage files are the evidence. When they disagree, the progress file is wrong —
a read that left no decision row behind is not a read.

### The fourth verdict: `unprocessed`

A handful of corpus items carry no readable text (42 of the 7,665 in
`corpus-pv.json`), and the fetch-once rule forbids re-fetching them. They get
`decision: "unprocessed"` with `read_by_agent: false` — the honest answer, and
the only case where a decision may be recorded without a read. §7 still forbids
reaching a *verdict* from a headline, and `unprocessed` is not a verdict: it is
the record that no verdict could be reached.

`unprocessed` is **not** an exclusion. Every counter reports it separately, and
its reason never enters the exclusion breakdown — folding it in would present a
stub nobody could read as a considered rejection. The allowed values live in
`batchlog.VERDICTS`; adding one means teaching every counter about it in the
same change, or it silently lands in some else-branch. That is not hypothetical:
it is how batch b022 reported 14 real complaints as exclusions.

Then write the changelog entry: what you learned, what you changed, and what you
propose but may not change yourself. Open it by checking whether the previous
cycle's changes actually helped — located share and verification accuracy — and
revert anything that made those worse.

**Not yours to change:** the honesty rules, the privacy rules, the read-only rule,
the rate limits. Proposals for those go in the changelog for a human.
