# Cycle changelog

## Decisión del operador — 2026-08-24 · Idioma: todo lo visible en español

El operador fijó la convención de idioma: **todo texto que ve una persona se
escribe en español** — la documentación, todo el texto del sitio web/panel,
los informes diarios y el campo `summary` de los registros nuevos. En inglés
quedan solo los identificadores de código (archivos, campos JSON, enums,
comandos). La regla está escrita en tres lugares para que ningún agente la
pierda: `README.md` («Idioma»), `EXTRACTION.md` (encabezado y §4) y el
documento rector `../vallarta_agent_prompt.md` (sección «Language», y el campo
`summary` del esquema ahora dice «in Spanish»).

**Qué se tradujo en este cambio**

- `README.md` y `EXTRACTION.md`: traducción completa al español, misma
  estructura y mismos nombres de archivo. (La sesión concurrente de la capa
  social ya está escribiendo sus adiciones sobre la versión en español.)
- `cycle.py report`: todo el texto generado del informe diario ahora sale en
  español — se muestra en la pestaña «Último informe» del panel, así que era
  texto del sitio en inglés. El informe de hoy se regeneró.
- `server.py`: el único mensaje de error en inglés que llegaba al navegador
  («Could not read the article index») ahora está en español. El resto de la
  interfaz (`web/`) ya estaba en español desde la traducción anterior.
- Cadenas de archivos de estado/datos que el panel muestra tal cual:
  `state/candidate_sources.json` (los campos `kind` y `why` de los 10
  candidatos — pestaña «Fuentes candidatas»), `state/vocabulary.json` (los
  `why` de los 4 términos en observación) y `data/audits.json` (las notas de
  las 2 auditorías — sección «Auditorías de calidad»). También el
  `reading_note` de `data/triage-2026-08-24.json`, que el informe diario cita.
  Solo se tradujeron los campos que se renderizan; los campos internos
  (`recon`, notas de nivel superior no mostradas) quedaron como estaban.
  Las zonas de `state/context_zones.json` ya estaban en español.

**Qué queda pendiente, y por qué no se hizo ahora**

- **~420 `summary` en inglés en `records.json` / `incidents.json`** — son el
  único texto en inglés que el panel sigue mostrando (una oración por tarjeta
  de incidente). No se tradujeron en esta pasada porque la lectura del corpus
  sigue corriendo y `store.py` reescribe esos archivos al ingerir
  (`records.json` se escribió minutos antes de este cambio); editar 420
  registros a mitad de esa corrida arriesga perder la edición o el lote en una
  colisión de escritura. Hacerlo en **una sola pasada al terminar la corrida**,
  respetando el tope de 25 palabras del validador, y anotarlo aquí.
- Los lotes en vuelo llevan en sus instrucciones la regla anterior («summary en
  inglés»), así que habrá summaries mezclados hasta esa pasada única. Esperado,
  no un defecto de los lectores.
- Las entradas históricas de este changelog permanecen en el idioma en que se
  escribieron, como registro; las nuevas se escriben en español. Los mensajes
  del validador de `store.py` y la salida de consola siguen en inglés (son
  salida de herramienta para el operador, no texto del sitio); traducirlos es
  opcional y de bajo riesgo si el operador lo quiere.

## Intake social — 2026-08-24 · CityPulse con Facebook exportado

Pedido del operador: integrar la idea de CityPulse — búsqueda por tema y fuentes
locales de Facebook — sin romper el esquema actual de registros/incidentes.

1. **Adaptador `social.py`.** Nuevo flujo de solo lectura: genera búsquedas para
   ciudad+tema, normaliza JSON exportado por scrapers externos de Facebook y
   produce `data/social-worklist-<fecha>.json` para clasificación LLM/humana.
   Después convierte items clasificados en `data/extract-social-<fecha>.json` y
   `data/triage-social-<fecha>.json`, listos para `store.py`.
2. **Dos caminos, un almacén.** `source_path` distingue `keyword_search` de
   `local_sources`, pero ambos terminan como registros normales. Comentarios usan
   una URL estable `#comment-...` para no chocar con la publicación madre.
3. **Privacidad y ubicación.** `author` es siempre `null` para Facebook; no se
   conservan nombres ni perfiles de personas. Una Página local prueba relevancia
   de ciudad, no colonia. Solo una fuente explícitamente acotada a colonia puede
   dar `location_basis: "source_colonia_scope"`; el resto depende de evidencia en
   el texto y del nomenclátor.
4. **Registro de fuentes.** `state/social_sources.json` queda como lista vacía y
   aprobada manualmente, con esquema para Páginas/grupos. Ninguna fuente social se
   consulta desde Codex; el archivo solo da metadatos a exportaciones ya obtenidas.

**Límite conocido:** el panel todavía muestra estos registros principalmente por
categorías (`drainage`, `trash`, `water`); los campos `topic`/`subtopic` ya viajan
en `records.json`, pero falta una vista dedicada tipo “Pollution · Puerto
Vallarta”.

## Dashboard feature — 2026-08-24 · Wildlife category and crocodile context zones

Operator request: crocodile sightings are a recurring public-safety issue near
the esteros and river mouths, previously squeezed into `other`.

1. **`wildlife` category.** Added to the enum in `store.py` and documented in
   `EXTRACTION.md` (dangerous fauna in public areas; pair with `public_space`
   when the complaint is about the response, not the animal). Keywords
   (cocodrilo, caimán, avistamiento…) join `vocabulary.json` — reading-order
   hints only, never qualification. The one existing crocodile record
   (INC-20260629-320, Marina Vallarta beach open after a fatal attack) was
   recategorized to include `wildlife`; its evidence and location are untouched.
2. **Context layer, viewer-only.** `state/context_zones.json` holds five
   operator-provided zones with known crocodile presence (Boca de Tomates /
   Ameca, Playa del Holi / Pitillal, Marina Vallarta / El Salado, Cuale mouth,
   Mojoneras), hand-estimated centres like `colonia_coords.json`. Selecting the
   🐊 category in either category filter draws them dashed-amber on the map and
   lists them above the incident cards, labeled as background context — they
   enter no count, no record, no metric. The 🐊 option is always offered even
   while incidents are scarce, because the context layer is useful on its own.
3. **Hot-zone toggle.** A map checkbox shades the 10 colonias with the most
   incidents under the current filter (same set as the side ranking). Filtered
   to 🐊, it will show where sightings concentrate as data accumulates — the
   hand-written zones are the prior, the shaded ones are the evidence, and a
   disagreement between them is a finding.

**Known limit:** zone circles are hand-estimated centres and radii, not habitat
boundaries; the map labels them as context precisely so nobody reads them as
measured data.

## Dashboard feature — 2026-08-24 · Collaborator credits and colonia ranking

Operator request: the frame should thank the people the data comes from, and
rank the reports by zone.

1. **Colaboradores tab.** The journalists whose articles became records, ranked
   by contribution (articles registered, incidents documented, located
   records), personal bylines above newsroom desks ("Redacción…"), with an
   honest count of how many records carry no identifiable author. Clicking a
   name filters the incident list to their work.
2. **Byline join, viewer-side only.** Only 36 of 420 records carry an `author`
   field, but the corpus index and the cached article pages know who wrote most
   of the rest, keyed by `article_url`. `server.py` joins them at render time;
   `records.json` is never modified. Byline text comes from the outlets' own
   metadata — nothing is inferred. Tribuna de la Bahía signs with initials
   (JB, LG), so a two-character byline is a valid name, credited as printed.
3. **Colonias tab.** Every colonia ranked by incidents (press coverage shown
   alongside as article counts, so a story the press returns to weighs
   visibly), with open/resolved splits, top categories, and last-report dates.
   Ranking stays at the colonia level — the unit the honesty rules let a
   record claim — and the panel states how many incidents have no colonia and
   therefore sit outside the ranking. No zone grouping is invented.

**Known limit:** most archive records predate byline capture, so 384 of 420
records remain uncredited until their cached pages or corpus rows carry an
author. The credit list understates prolific reporters accordingly, and the
panel says so.

## Reporting cleanup, round 2 — 2026-08-24 · Two workflow generations, one set of filenames

**Previous-change review:** the reporting fixes earlier today held. The audit
they introduced then found the problems below, which is what it was for. One
inference in that entry was wrong and is corrected here.

**Correction to the previous entry.** It reported 238 articles as "marked
processed but never read". They *had* been read. When habitat-14 stopped its
first workflow, nine in-flight agents were not killed; four of them finished
full 60-article reads and logged them. The second-generation agents for the same
batches used the same filenames, found their URLs already in `processed_urls`,
wrote empty triage files over the first generation's completed ones, and logged
`scanned=0`. The reads were real; the evidence was destroyed by a file
collision between two workflow generations. habitat-14 recovered all 300
verdicts from the reading agents' transcripts and re-materialised them; the
restored URL sets match the assignment files exactly and all five batches were
100% exclusions, so no record was ever at risk.

"Unread" was the safe inference from the evidence on disk and the safe thing to
raise loudly, but it was not the true one, and `data/requeue-untriaged-2026-08-24.json`
describes a problem that did not exist. It is left in place with its timestamp
as a record of what the pipeline looked like at that moment; nothing needs
requeuing from it.

**What was actually wrong, and is now fixed**

- *The same work was logged twice.* Each of the four batches had two progress
  entries — the zombie agent's (`archive-2026-08-24-b101/103/106/108`, counts
  right) and the second generation's (`archive-full-…`, `scanned=0`) — both
  pointing at the same triage file. The corpus was being counted twice over.
  The `archive-full-` entries now carry counts derived from their files, and the
  duplicates are marked `superseded_by` with a note rather than deleted: the
  double log is itself a fact about how this corpus was read.
- *The restored files did not say they were restored.* All five read as though
  written at read time. They now carry `restored_from_transcript` and a
  provenance note in the reading note. The verdicts are the reader's own, but
  the evidence chain runs through a transcript rather than straight from the
  read, and a file that hides that is weaker evidence pretending to be stronger.
- *`unprocessed` was half-wired.* habitat-14 added it as a fourth verdict for
  the 42 text stubs — correct, and it is the honest handling — but three
  counters still had it falling into their else-branch and being reported as an
  *exclusion*, with its reason code polluting the exclusion breakdown. Fixed in
  `batchlog.py`, `server.py._batches()` and the audit. The allowed values now
  live in `batchlog.VERDICTS` and are imported, so the next verdict added cannot
  drift out of sync with the things that count it. This is the b022 defect
  recurring one layer up, within hours, which is the argument for the constant.

**Two new detectors in `readqueue.py audit`**

- A logged batch whose triage file holds fewer decisions than its logged
  `scanned` has lost evidence since it was logged. This is what exposed the
  double-logging: eight entries for four batches of work, four claiming 60 with
  an empty file and four claiming 0 with a full one.
- Batches marked `superseded_by` are reported as an expected duplicate rather
  than a discrepancy.

`batchlog.py` also now refuses a batch with **no decisions at all**. A batch that
read nothing is never a valid outcome under read-everything; it means an agent
inferred "already done" from `processed_urls`, which is a summary and not
evidence. That guard fired correctly on a retry during the live run.

**The dashboard crashed twice on the same shape of bug.** `_cycles()` assumed
every triage file carries the key it expects. First it required `cycle` and
archive batches carry `batch` (a 500 on `/api/data` since batch b001). Then,
after classification moved to "is this id logged as a batch", an in-flight file —
written but not yet logged — fell through to the daily-cycle branch and crashed
on the same line. The identifier is now resolved once in the classifier and
handed to the consumers, and a written-but-unlogged archive batch is its own
`pending` state rather than being mistaken for a daily cycle.

**Documented in EXTRACTION.md §8**
- `readqueue.py next` is for a **single interactive reader**. It hands out
  whatever is unclaimed at the instant it runs, and a claim is invisible to
  others until the batch is logged, so concurrent readers get overlapping work.
  Fan-out must use fixed pre-cut assignments. Worth recording why: this rule was
  written into §8 as a recipe earlier today, and about ten fan-out agents
  weighted the document over their own instructions and self-organised into
  20-article queue draws. A document that describes a single-reader tool without
  saying so will be followed by agents for whom it is wrong.
- Never conclude "nothing to read" from `processed_urls`.
- The `unprocessed` verdict: what it means, when it is valid, and that it is not
  an exclusion.

**Still open**
- The b113 class can recur: a retried agent can overwrite a completed triage file
  before the empty-batch guard fires at the log step. Recoverable from
  transcripts, and the audit's new count check detects it, but the write itself
  is unguarded.

  **Decided, by habitat-14, after this was raised:** generation-scoped filenames
  and batch ids remove the class and are adopted — but not mid-run. The ~70
  remaining agents carry the current filenames in their prompts; editing those
  invalidates the workflow's resume cache and re-runs completed work. The
  residual hazard is now bounded (all first-generation zombies are accounted
  for, so it is limited to same-batch retries within this run) and it is caught
  between batches by the audit's count check. Recorded here rather than left to
  read as an oversight: the run rides it out with the detector, and the
  generation goes into both the filename and the batch id for any makeup batches
  and any future workflow generation.
- 22 articles were read twice in b001–b050, four pairs disagreeing on exclusion
  reason code. Unchanged from the previous entry and still worth a §2 pass.

## Reporting cleanup — 2026-08-24 · Making the output match the read-everything rule

**Previous-change review:** the operator abolished screening earlier today and
`EXTRACTION.md` §7/§8 were updated. The *code* was not. Everything downstream of
the decision still described a filter that no longer exists, so the pipeline was
telling readers the opposite of the rule it was running under. This entry closes
that gap. No extraction work is in this entry — the remaining 6,509-article read
is running from habitat-14's multi-agent workflow, which took the whole backlog.

**Screening removed from the code, not just the docs**
- `sample.py screened` retired. It sampled the discarded pile to catch a filter
  swallowing real complaints; there is no discarded pile. `verdict --kind
  screened` still parses so the audit already in `data/audits.json` keeps its
  vocabulary.
- `prefilter.py` / `quick_rank.py`: tiers renamed `read`/`maybe`/`screened_out`
  → `priority_high`/`priority_medium`/`priority_low`. The rename is the point —
  a low score now changes *when* an article is read, never *whether*.
- `data/ranked-pv.json` is deliberately **not** regenerated. It carries the old
  labels, which map 1:1 onto the new tiers. It is the frozen reading order for a
  read in progress, and rescoring it against a vocabulary that has grown since
  would shuffle the queue under the readers mid-run.

**The dashboard was making a false claim to anyone who opened it.** The Cribado
tab reported "descartados sin leer: 5,707" — that nearly three quarters of the
corpus had been discarded unread. That was true under the old rule and false
under the new one. It is now a Lectura tab: read so far vs not yet read, tier
counts as reading order, pending-by-outlet, and a next-in-queue table.
`server.py` grew `_reading()` in place of `_screening()`.

**`cycle.py report` now separates read-so-far from not-yet-read**, sourced from
the archive progress files, and says in the report itself that a qualified count
drawn from part of a corpus describes that part and nothing else. The old
"machine-screened vs read by the agent" block is gone; in its place, an article
triaged *without* a full-text read is now reported as a defect rather than as a
policy, because that is what it is now.

**Three defects found by reconciling the progress file against the triage files**

The progress file is a summary; the triage files are the evidence. They
disagreed:

1. *A claimed read with nothing behind it.* One URL sat in `processed_urls` with
   no triage decision in any batch file. Its record was in fact already in the
   store (INC-20260717-140) — the extraction survived and the triage row was
   lost. The article was re-read from the corpus and triaged independently
   before the stored record was consulted; the two agreed on every field. Only
   the missing decision row was restored, in
   `data/triage-archive-2026-08-24-orphan01.json`. No new record was created.
2. *14 qualifying articles were being reported as excluded.* Batch b022 wrote
   `decision: "qualified"` instead of `"yes"`. Every consumer in the pipeline
   treats an unrecognised decision as an exclusion, so 14 real complaints were
   counted as rejections in the progress file and would have been in every
   report. The records themselves were correct and all 14 are in `records.json`
   — only the verdict string was wrong. Corrected, and b022's logged counts
   recomputed. Its entry had also been internally inconsistent (20 scanned,
   0+1+5 accounted for) and nothing caught it.
3. *22 articles were read twice* across b001–b050 — wasted effort rather than an
   error, since `processed_urls` is a set and no duplicate records reached the
   store. Four of the pairs disagreed, all on the exclusion reason code and none
   on qualification: `off_topic_other` vs `off_topic_crime`, `event_not_complaint`
   vs `out_of_area`, `off_topic_politics` vs `out_of_area`, `off_topic_other` vs
   `official_statement_no_problem`. No record is affected, but it shows the
   reason-code taxonomy is applied inconsistently between reads. Worth watching
   as batch volume rises; §2 may need sharper boundaries between `out_of_area`
   and the topic codes.

**New tooling, built because two sessions are now reading one corpus**
- `readqueue.py` — `status`, `next` (yields not-yet-read articles in reading
  order with full text inline), and `audit`, which is what found all three
  defects above. Run it after any fan-out of batches.
- `batchlog.py` — logs a batch under an `flock` and derives counts from the
  triage file instead of hand-typed numbers. It now **refuses** a batch whose
  decisions fall outside `yes`/`unsure`/`no`, or whose decisions do not say
  whether the article was read. Defect 2 above is the reason both checks exist.

**A crash nobody had noticed.** `server.py` `_cycles()` read every
`data/triage-*.json` and required a `cycle` key. Archive batch files carry
`batch` instead, so the dashboard has been returning a 500 on `/api/data` since
batch b001 — the entire dashboard, not just one tab. Daily cycles and archive
batches are now told apart; batches are summarised in the reading panel rather
than being dumped into the daily trend line, where 111 rows against one date
would swamp it.

**Coordination note.** habitat-14 pre-cut the remaining backlog into
`data/fullread-batches/b101..b211.json` and said it was taking the back of the
queue while this session kept the front. Checked rather than assumed: the
pre-cut covers all 6,509 remaining articles, front to back, and leaves nothing
unclaimed. Acting on the stated split would have double-extracted. It is also
writing batch ids `archive-2026-08-24-b051…b060`, not the `archive-full-…-b1xx`
it announced, which is the range this session had said it would continue into.
Both discrepancies were reported back. The lesson is cheap and general: verify a
peer's claim about what it has claimed before writing against it.

**Not changed, and flagged for the operator**
- The 25 articles in the retired screened-sample audit were judged from
  headlines. They are not in `processed_urls`, so they fall inside habitat-14's
  claim set and will be read properly. No action needed, but they are not yet
  read as full text and should not be counted as read.
- 42 of the 7,665 corpus items carry near-empty text. They cannot be honestly
  triaged from the corpus, and the fetch-once rule forbids re-fetching them.
  They need either a human authorisation to re-fetch or an explicit
  `unprocessed` decision — they must not be triaged from their headlines.

## Operator decision — 2026-08-24 · Screening abolished: read everything

The operator ordered the corpus-scale screening rule removed. Effective now:
every article in every corpus is read as full text and triaged — nothing is
`screened_out`, and the prefilter ranking survives only as reading order.
`sample.py screened` is retired. EXTRACTION.md §7/§8 updated accordingly.
The honesty rule is unchanged: the triage file still records what was actually
read, and reports must separate *read so far* from *not yet read* until the
full-corpus read completes. Feasibility note: `corpus-pv.json` carries full
article text locally (median ~2,100 chars; 42 of 7,665 items near-empty), so
the full read requires no re-fetching and does not touch the rate limits.

## Protocol extension + scan — 2026-08-24 · Meridiano and Banderas News approved

**Previous-change review:** cycle 5's NoticiasPV extension produced 5 qualifying
records from 10 items — a far higher hit rate than the original three feeds —
and located share held at 70% all-cycle. Nothing reverted.

**Operator decision:** after a recon of 11 candidate outlets, the operator
approved two new sources: Meridiano (`https://meridiano.mx/feed/`, Nayarit
edition, in scope only for Bahía de Banderas coverage) and Banderas News
(`https://banderasnews.com/feed/`, English-language). Both were added to
`state/sources.json` and the prompt's source list. Rejected by recon and logged
in `state/candidate_sources.json`: La Noticia al Punto Vallarta (feed live but
currently serving multilingual casino spam — site likely compromised; do not
add without re-checking), PV Mirror (stale since Dec 2025), Out & About PV
(lifestyle only), Reporte Diario / Vallarta Today (no feed), Vallarta Opina
(broken self-signed TLS, no feed), NotiVallarta (domain dead).

**Run (sub-cycle 2026-08-24-newsources):** the two new feeds returned 20 items;
all were read from full RSS body text (both publish `content:encoded`) and all
20 were excluded — Meridiano's batch was Tepic officialdom and politics,
Banderas News was culture/lifestyle plus one `official_statement_no_problem`
(Amado Nervo bridge 90% complete, opening Nov 2026 — worth watching as context
for Federal Highway 200 congestion complaints, not a complaint itself). Zero
records added, so store/learn/report were not run; decisions are in
`data/triage-2026-08-24-newsources.json`.

**Also:** full article pages for the five cycle-5 NoticiasPV records were
fetched (once each, 5 s apart) and are now in `cache/pages-raw/`; an independent
full-text re-read of all five reached the same verdicts, categories and
locations as the excerpt-based records — a free accuracy check, 5/5 match.

**Rate-limit disclosure:** during recon each new feed was read twice (probe +
content sample) before `feeds.py` read it a third time the same day. Three
light reads on day one exceeds the twice-per-day cap; recorded here per the
honesty rules. From tomorrow the ledger enforces the normal cap.

**Expectations to check next cycle:** Meridiano may be near-zero yield outside
hurricane/flood events in Bahía de Banderas — if it stays zero for several
cycles, propose demoting it. Banderas News is likely low-yield but useful for
official works context in English.

## Cycle 5 — 2026-08-24 · NoticiasPV collection and extraction

**Previous-change review:** the NoticiasPV source extension left the all-cycle
located share at 70% (127 of 181 records after ingestion). This cycle's located
share was 40% (2 of 5 new records), because three city-wide NoticiasPV complaints
had no defensible place. The weekly quality check re-read 10 cached source texts,
found 0 mismatches, and measured 100% accuracy. No change was reverted.

**Run:** the fourth approved feed returned 10 items. The combined worklist held
45 items; all 45 RSS texts were read. Seven qualified, one remained `unsure`, and
37 were excluded. Five new NoticiasPV infrastructure records were accepted, all
from RSS excerpts because their pages had been fetched before protocol approval
and were not re-fetched. No new article page was fetched for NoticiasPV.

**Incidents:** five new incidents opened, none merged. The new complaints cover
unmaintained waterways, open drains, illegal dumping, recurrent flooding at the
CUC access road, and failed traffic signals at Carretera 544/Avenida Federación.
The gazetteer grew by three evidence-backed entries: two streets and the CUC
landmark. No new colonia was asserted.

**What changed:** `cycle.py` now uses the exact extraction batch when reporting
same-day runs, preventing already-known records from being counted as newly
opened incidents on a rerun. Existing rate limits, fetch-once, RSS-excerpt
honesty, privacy, location evidence, and duplicate rules remain unchanged.

## Protocol extension — 2026-08-24 · NoticiasPV approved

**Previous-change review:** the latest cycle's located share remains 67% (2 of 3
records); verification accuracy is not yet measurable because the weekly audit
needs 10 records. No prior change was reverted.

**Operator decision:** NoticiasPV was added as an approved Puerto Vallarta source
at the operator's request. Its RSS feed is `https://www.noticiaspv.com.mx/feed/`.
The feed returned 10 items during recon. Its WordPress REST posts endpoint also
responded successfully, so archive backfill can use the REST method. The site's
robots file disallows GPTBot and SemrushBot only; it has no rule for this
fetcher's user agent.

**What changed:** the governing source list, active feed registry, daily fetcher
fallback, archive plan, README, and candidate-source note now describe four
approved feeds. Existing rate limits, five-second page spacing, fetch-once,
read-only, privacy, and extraction rules are unchanged. No NoticiasPV article
was triaged or ingested in this change.

**Next run:** collect NoticiasPV alongside the other three feeds, then read and
triage its items under the same qualification and duplicate rules.

## Operator task — 2026-08-24 · colonia master list set + external-source recon

**Authorisation.** The operator directed both tasks; the colonia master list is
the human-supplied decision `coverage.json` was waiting on (the operator chose
the sources), and all web access below was read-only, ≥5s between requests,
robots-respecting.

**Colonia master list: SET — 174 names.** Built from the union of, in priority
order: (1) postal-code asentamientos for CP 48280–48399 via the Zippopotam API
(full polite sweep, 42 assigned CPs, 132 names; aggregated postal data, not
official SEPOMEX), (2) 23 OpenStreetMap-only places/residential areas (OSM
alone was tried first and yielded just 26 places over four query strategies —
too sparse to use alone), and (3) 19 colonias already heard from in news
records that neither source contained (Mojoneras, Las Juntas, El Progreso…).
That third group proves the list is a **floor, not a complete inventory** —
blind-spot analysis now runs, but "not on the list" stays weaker evidence than
"on the list and silent". Per-name provenance: `state/colonia_master_list.draft.json`.
Known issues for future cycles: probable OSM typos ("Jardiens del Sol",
"Santa Fa Fracc.") kept verbatim rather than guessed at; name variants like
"Pitillal"/"El Pitillal" not yet reconciled.

**External-source recon: all six targets currently unusable for automated
reading** (details with per-endpoint status codes in
`state/source_recon-2026-08-24.json`): SEAPAL (no feed/API), CFE (SharePoint
site, no outage page found), municipal site (403 to non-browser clients
despite permissive robots.txt), datos.jalisco.gob.mx (DNS dead) and federal
datos.gob.mx (CKAN API gone), SMN/CONAGUA (no working API), Reddit
(unauthenticated JSON now 403; a registered OAuth app would work).
`candidate_sources.json` unchanged — nothing qualified.

**Proposed, needs a human:** (1) a transparency request to the municipality
for the citizen-complaint log — the strongest path to resident-sourced data
and immune to the website's 403s; (2) a free registered Reddit OAuth app if
r/puertovallarta is wanted; (3) manual or browser-based review of
SEAPAL/municipal announcements, which are published for humans only.

## Cycle 4 — 2026-08-24 · second daily feed read and extraction rerun

**Previous changes:** the located share remains **67% (2 of 3 records)**. Verification accuracy is not yet measurable because the store has only three records; the weekly audit therefore remains pending. No change was reverted on those metrics.

**Run:** the second permitted feed read returned 35 unique items. I read all 35 published RSS texts and retained the same three judgements: two qualified complaints and one `unsure` water-supply article. The other 32 decisions remain explicit in `data/triage-2026-08-24.json`. The validator rejected nothing, and the existing three article records were correctly skipped rather than duplicated.

**What I learned:** this feed snapshot added an accident outside Puerto Vallarta and a scheduled veterinary-service announcement, neither of which is a complaint. No new qualifying vocabulary, evidence-backed place, or candidate source was found.

**What changed:** refreshed the worklist, triage, extraction, and daily report. Repaired a same-day rerun artifact in the gazetteer by restoring one count per record and one canonical key for Brisas del Pacífico. The source-access, privacy, location-evidence, and read-only rules were unchanged.

**Still pending:** re-read 10 records once the dataset reaches that size; do not treat the current three-record check as a 90% verification result.


Newest cycle first. Every entry opens by checking whether the previous cycle's
changes actually helped, measured by located share and verification accuracy.

## Cycle 3 — 2026-08-24 · Guadalajara removed, Vallarta corpus published

**Guadalajara was out of scope and is gone.** The operator corrected the "gdl"
request: only Puerto Vallarta is relevant. Its records, incidents, reports and
gazetteer moved to `data/removed-gdl/` and the city was moved to `inactive_cities`
in `state/sources.json`. Parked rather than deleted, because the Jalisco
statewide outlets do carry Puerto Vallarta coverage and may be worth proposing as
sources later — that would be a human decision, not an assumption.

**The killed backfill had already paid for itself.** 70 cached pages held 6,998
Tribuna articles (2026-02-06 to 2026-08-24), so the corpus was rebuilt offline
with `archive.py --offline`, making zero requests. Diario de Vallarta was added
over the same span for four more requests. Corpus: **7,665 articles**, 219x the
35 a single feed read returns.

**Bug found while rebuilding.** The first offline run produced 3,999 articles from
7,000 cached posts and the shortfall looked like data corruption. It was not: the
cache holds 6,998 distinct ids with almost no duplication. `--limit-per-outlet`
had silently defaulted to 4,000. Worth recording because the failure mode —
a plausible-looking number from a silent cap — is exactly what the "no silent
caps" rule exists to catch. The corpus now states its own bounds in a `note`.

**Articles are on the site.** A new Artículos tab lists every scored article with
its score, bucket, matched categories and evidence snippet, filterable by text,
bucket, category, outlet and date, with an "only extracted" filter. The ranked
file is 5.4 MB, so `/api/articles` filters and pages server-side; the main payload
stays at 28 KB. Scores are displayed as what they are — a reading queue, never a
qualification.

**Corpus coverage is uneven, and the site says so.** Vallarta Independiente is
absent: its robots.txt disallows the bulk API, so it needs ~105 paged feed
requests (~10 minutes) that have not been run. Any per-outlet comparison drawn
from this corpus is therefore invalid until that gap is closed.

**Note on the UI.** The dashboard was translated to Spanish outside this session.
The new tab follows that, reusing the existing `BUCKET_LABEL` / `REASON_LABEL`
maps rather than introducing a second vocabulary.

## Cycle 2 — 2026-08-24 · Guadalajara / ZMG (operator request)

**Scope change.** The operator stopped the Vallarta archive backfill mid-run and
asked for the quickest available Guadalajara data. The year-long backfill was
killed at 70 cached pages (kept, not discarded). Guadalajara is a second city in
`state/sources.json`, with its own record store, gazetteer and reports, so
neither city's numbers contaminate the other's.

**Feeds found** (probed 14 candidates, 6 live): El Informador (Jalisco), El
Occidental, UDG TV, Quadratín Jalisco, Partidero, ZonaDocs. NTR Guadalajara and
Milenio's advertised feed both 404. 210 articles in about 30 seconds.

**The prefilter failed on this corpus and was overruled.** It screened out 202 of
210 and surfaced zero "read" items. Cause: the vocabulary was built from a single
day of Vallarta articles, so Guadalajara wording and the ZMG municipality names
were missing, and El Occidental's national wire dominates its feed. All 210
headlines were therefore read by hand. This is the failure the previous entry
predicted; it is recorded rather than smoothed over, and the triage file states
plainly which articles were read as text and which were judged from the headline.

**Results:** 6 qualified, 3 unsure, 9 records, 5 incidents, located share 44%
(down from 67%, on a much larger and less local corpus).

- The SIAPA contaminated-water megamarch was covered by four outlets and merged
  into one incident with `coverage_count` 4 — the clearest public-pressure signal
  the dataset has produced so far.
- One UDG TV article on Tonalá storm flooding names **seven** distinct located
  points. See the limitation below.

**Bugs found by inspecting output, then fixed**
1. Compound place names never merged: "vertederos de Laureles y Coyula-Matatlán"
   and "Laureles y Matatlán" are the same site but produced two incidents.
   `norm()` now drops generic place nouns and connectors, and landmarks are split
   like corner streets. The two landfill articles now merge; the Vallarta
   corner-street regression still passes and still refuses the wrong merge.
2. The daily report miscounted incidents, calling an incident's own opening
   article a "merge". New incidents opened vs. articles merged are now counted
   from each incident's first article.
3. Raw HTML was discarded after parsing. With "never re-fetch" in force, a parser
   bug would have been permanent. Raw pages are now kept in `cache/pages-raw/`.

**New capability:** `same_incident_as` lets a record state explicitly that it
covers the same event as another article. Automatic merging requires a location
match on both sides, so unlocated coverage — like the four march articles — would
otherwise never merge. The link is an agent judgement, recorded as
`linked_by_agent` on the incident, and is never inferred.

**Limitations that stand**
- *El Informador page extraction fails.* The parser picked up a sidebar headline
  instead of the article body. Those three records were built from the outlet's
  own RSS excerpt, which is real published text but short — the triage file marks
  them `extraction_source: rss_excerpt`. Because raw-HTML keeping landed *after*
  those three fetches, and the fetch-once rule forbids re-fetching, they cannot be
  re-parsed without human authorisation to re-fetch.
- *One record per article cannot hold seven places.* The Tonalá article locates
  flooding at seven separate crossings and colonias; the schema permits one. The
  record keeps the worst point (Bosques del Sol, 60 cm) and says "seven points" in
  the summary, so six real locations are not in the dataset.

**Proposed for human decision**
- A `sub_locations` array, so a multi-point article is not flattened to one place.
- A `municipality` location-certainty level between "approximate" and "none".
  City-wide utility failures — the Vallarta water crisis, the AMG water quality
  complaint — are currently recorded as "none", which understates what is known
  and depresses the located-share metric.
- Whether to re-fetch the three El Informador pages once the parser is fixed.

## Cycle 1b — 2026-08-24 · archive backfill (human-authorised)

**Authorisation.** The prompt makes the rate limits a human-only decision. The
operator asked for roughly 100x the article volume and then to raise the limit
further, which is that decision. Recorded here so the scope change is visible and
reversible, not folded silently into the method.

**What changed, precisely**
- Added `archive.py`, which reads each outlet's public archive over a one-year
  window (2025-08-24 → 2026-08-25) instead of only the newest feed items.
- Everything else in the source rules is unchanged: read-only, 5 seconds between
  requests, one fetch per URL ever, facts saved rather than article text.

**robots.txt governs the access method, per host**
- `tribunadelabahia.com.mx` — robots allows everything → WordPress REST API.
- `diariodevallarta.com` — only `/wp-admin` disallowed → REST API.
- `vallartaindependiente.com` — **`Disallow: /wp-json/`**, so the API is off
  limits there. Paged RSS is used instead, which robots does not disallow. Its
  `crawl-delay: 5` matches the gap we already keep.

Bulk endpoints return the article body inline, so the corpus costs ~230 requests
rather than ~15,000 page fetches. The larger corpus is the *gentler* option.

**New integrity problem this creates, and the fix**
A day's 35 articles can all be read. 15,000 cannot. `prefilter.py` scores every
article against the vocabulary and sorts it into read / maybe / screened_out.
Two rules keep this honest:
- the filter never decides that an article *qualifies* — only what gets read;
- `screened_out` articles keep their score and reason and are never deleted, so
  the pile can be sampled to catch a filter that is swallowing real complaints.

Consequently the daily report must stop saying a flat "scanned". It now separates
**machine-screened** from **read by the agent**, because claiming to have read
15,000 articles would be false.

**Watch for**
- Vocabulary built from one day of articles will be too narrow for a year of
  them. Expect the first pass to over-screen; sample the screened-out pile before
  trusting the qualified count.
- Feed-derived text for Vallarta Independiente may be truncated relative to the
  REST-derived text from the other two, which could bias its located share
  downward. Compare per-outlet located shares before drawing conclusions.

## Cycle 1 — 2026-08-24

**Review of previous cycle:** none. This is the first cycle; the numbers below are
the baseline, not evidence of improvement.

**Baseline numbers**
- articles scanned 35, qualified 2, unsure 1, excluded 32
- located share (exact + approximate) 67% (2 of 3 records)
- verification accuracy: not yet measurable — the weekly 10-record re-read needs
  a larger pool than 3 records. First quality check due once ≥10 records exist.

**What I learned**
- *Gazetteer seeded* with 6 evidence-backed entries: streets Avenida Francisco
  Villa, calle Viena, Calle Alemania, avenida Víctor Iturbe; colonia Brisas del
  Pacífico; landmark Conalep 1.
- *Vocabulary gap found.* "registro abierto" is the local wording for an
  uncovered manhole. A drainage keyword list built from "drenaje / alcantarilla"
  alone would have missed the headline entirely. Promoted to the active list.
- *Feed text is often enough.* Both qualifying articles were identifiable from the
  RSS body; full pages were fetched only to confirm bylines and to settle two
  borderline calls. That keeps the request count low without losing anything.
- *An anti-keyword list is as useful as a keyword list.* 20 of the 32 exclusions
  were crime or national politics, several using the word "denuncia".

**What I changed**
1. Added `state/vocabulary.json` with active terms, a watch list, and
   anti-keywords, so triage reasoning is written down instead of improvised.
2. Made the store's validator enforce honesty rule 1 mechanically: a `street`,
   `colonia` or `landmark` is rejected unless its words appear in
   `location_evidence`. It rejected two of my own first-pass records — the fix was
   to correct the evidence, not to loosen the check.
3. Unlocated records never auto-merge into an incident (`same_incident` requires a
   place match on both sides), so "location unknown" cannot silently swallow
   unrelated complaints.
4. A corner ("Francisco Villa esquina Viena") is split into both street names for
   duplicate matching. Found by inspecting the first incident file: as originally
   written, a follow-up article naming only one of the two streets would have been
   filed as a separate incident and the `coverage_count` signal would have been
   lost. Regression-tested: such a follow-up now merges, and does not merge into
   the unrelated water incident.

**Known limit, not yet changed**
- The one-quoted-phrase-per-record rule cost a true fact: the Brisas del Pacífico
  leak reached the "centro cultural La Lija", but that landmark sits in a
  different sentence from the colonia and street, so recording it would have
  needed a second quote. The landmark was dropped instead of asserted.

**Proposed for human decision** (cannot change these myself)
- Allow a second short evidence phrase, or a separate `landmark_evidence` field,
  so a landmark in another sentence can be kept honestly. This touches the
  quoting rule, so it is a human call.
- Supply an authoritative Puerto Vallarta colonia list (municipal or INEGI).
  Blind-spot analysis is impossible without one, and inventing a list would break
  the rule against fabricated place names. `state/coverage.json` holds the gap.
- Approve or reject the three candidate sources in
  `state/candidate_sources.json`. None are being read.

**Hypotheses to test next cycle**
- Complaint articles cluster in Tribuna de la Bahía's "Puerto Vallarta" section
  and Vallarta Independiente's local desk; the volume from Diario de Vallarta may
  be near zero. If three cycles confirm that, say so rather than assuming the
  feed is broken.
- A 2-of-35 qualifying rate is low. Either genuine complaints are rare in a single
  day's feed, or the feeds carry only the newest ~10-20 items and the daily read
  is missing articles published between reads. Watch for URL gaps.
