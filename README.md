# Wildfire Signals (pre-release)

**Codex çalışma klasörü:** Bu deponun kök dizini (`wildfire-signals/`).
Proje için Codex'i bu klasörde açın; [AGENTS.md](AGENTS.md) canlı/yerel çalışma
sınırlarını açıklar. Harita ve açık veri toplama GitHub Actions ile Cloudflare'da
çalışır; bu bilgisayarda Docker veya model çalıştırılması gerekmez.

This is the public, standalone collector and map. It contains no private repository
history or credentials. The [preview map](https://wildfire-signals.pages.dev/)
is live with hourly hosted collection. It is not a stable 1.0 release.

## Data meaning

- NASA FIRMS VIIRS NOAA-20 and NOAA-21 pixels are grouped into 0.05-degree,
  one-hour **satellite candidates**. A candidate does not establish a fire.
- NIFC WFIGS `WF` and Canadian CWFIS `OC`/`BH`/`UC` active fire records are separate
  **agency incidents**.
- The time window filters satellite observations. Agency records come from the
  current source layer; their source update date can be older than collection.
- The 72-hour view now uses a rolling 72-hour FIRMS window from four UTC calendar
  dates. The 6- and 24-hour views filter the same snapshot in the browser.
- Nearby satellite candidates and agency incidents may be linked **provisionally**
  by point distance. This does not confirm a fire or establish common identity.
- Source failures produce `partial` status; a complete upstream outage keeps the
  previous published snapshot.

The map's visible-area analysis summarizes candidate cell-hours, distinct 0.05-degree
cells, cells observed in multiple hours, the latest observation, and counts in the
two halves of the selected time window. It uses the current map viewport, not a
country boundary. The comparison is observation activity, not a measure of fire
growth. Failed VIIRS sources are shown with the summary; no-data during an outage
must not be read as no fire. The map does not retain fire incidents or burned-area
perimeters after the 72-hour candidate window.

The verified FIRMS SQLite database can also feed the existing
[Historical Intelligence Workbench](docs/workbench-verified-firms-pixels.md)
using `--pixel-db` in both `report` and `compare`. Raw VIIRS pixels and
0.05° candidate cell-hours are labeled separately; agency histories retain
independent identities, with no double-counting of both satellite archives.
This is an offline evidence research interface, not a validated forecast.

The next step is the [GitHub research release sync](docs/research-release-sync.md):
`python -m fire_public.release_sync` discovers recent dated research Releases,
downloads and SHA-256-verifies their FIRMS pixel assets into per-day atomic
directories, imports complete sets into local SQLite, and generates worldwide
point-in-time source coverage reports. It has strict network/download budgets,
does not enable or run any public collector, and does not claim that missing
observations mean no wildfires. The researcher owns the local backup.

The [Historical Intelligence Workbench integration](docs/workbench-official-perimeter-evidence.md)
can now include separately archived **retrospective NIFC official fire polygons**
with `--perimeter-db` in both `report` and `compare`. The feature keeps them
separate from current incident IDs, satellite thermal candidates and weather
evidence; it reports when polygon versions were actually archived rather than
claiming the original fire year was a prospective source-availability date.

The [independent label review workbench](docs/independent-label-review-workbench.md)
closes the research handoff from archived real NIFC polygons and a separately
documented region-time sampling frame into a deterministic **unlabeled review
queue**. It refuses pseudo-negative labels, requires two agreeing human reviewers
plus an additional independent negative-window coverage attestor, checks event,
source and feature availability times, and only then exports a
`labeled_evaluation`-compatible private cohort with source SHA-256 provenance.
The existing real NIFC CI can now demonstrate an unadjudicated eight-real-source
queue with explicitly synthetic control units; **no true negative samples or
measured prediction skill are created by these integration tests**.
The [immutable official NIFC context archive](docs/official-source-context-archive.md)
now links real fixed-endpoint source refresh responses to the exact historical
review queue in a separate SHA-256-verified `official-context/` namespace.
Offline audit replays original government GeoJSON and detects altered source
bytes; the private reviewer form can optionally display source revision/capture
status without pre-filling outcomes. These records **never enter independent
positive/negative label receipts** or imply valid nonfire data.

The [official NIFC lead source reconciliation](docs/official-lead-source-reconciliation.md)
directly re-queries the pinned US government ArcGIS HTTPS layer for archived
review-queue perimeter identities, compares original and fresh source feature
hashes, and preserves **raw provider GeoJSON bytes** with a reproducible audit
of source revisions. The existing real NIFC eight-lead CI tests this against
the actual provider; records remain retrospective positive-context evidence,
not automatically valid binary event outcomes or fire-negative labels.

The optional [negative registry geographic and temporal admission gate](docs/negative-registry-coverage-gate.md)
now requires a sampled unit's complete WGS84 study footprint to fit inside
the **independently declared** source's rectangular scope and a continuous
observation interval across the full prediction horizon, with no unknown
or outage periods. It binds the exact registry source URL and record ID to
SHA-256-archived third-reviewer evidence and blocks strict cohort export if
any negative case fails. A registry's completeness remains an operator claim,
**not verified no-fire ground truth**.

The [independent evidence receipt archive](docs/independent-evidence-receipts.md)
lets a researcher preserve original privately acquired source documents using
content-addressed SHA-256 blobs and capture-time receipts. The optional
`label_review finalize --evidence-store` strict gate checks every adjudicated
label's reviewer/source URLs, source record IDs and full negative-registry
coverage window against archived bytes **before cohort export**. The archive
never fetches arbitrary URLs or claims to authenticate original publishers,
valid nonfire outcomes, or external reviewer independence.

The [offline interactive reviewer form](docs/offline-reviewer-form.md)
turns each private independent review packet into a self-contained browser
interface with explicit per-case votes or abstentions, independent evidence
attestation and a downloaded JSON vote file compatible with the existing
blind reconciliation pipeline. It requires no server, external requests or
browser persistence, and historical NIFC source leads cannot be voted
fire-negative. Browser tests cover desktop/mobile workflow and file download.
It is not automated ground truth verification.

The offline [blind review intake](docs/independent-label-review-workbench.md#independent-reviewer-intake)
produces private per-reviewer HTML briefs and vote forms, preserves disagreements,
and passes only matching independently recorded votes to the same cohort gate.
Its [sampling and attrition audit](docs/independent-label-review-workbench.md#sampling-and-review-attrition-audit)
exports private HTML/JSON with separate NIFC source and independent frame denominators,
review losses and an explicit prohibition on interpreting selected-case counts as
population fire prevalence.

The [official NIFC sampled-source quality audit](docs/nifc-source-quality-audit.md)
checks stored agency polygon integrity before producing year-by-year field-missingness,
reported acreage, vertex/degenerate-geometry and exact duplicate-shape review
summaries. It exports static HTML and JSON, with observed fractions denominated
by **downloaded government records only**, and explicitly identifies missing
negative wildfire labels. The existing bounded *real-source* multi-year CI
now produces both quality reports from its already captured dataset, without
more government API requests.

The [CAL FIRE alternative-event casebooks](docs/calfire-alternative-event-dossiers.md)
explain why seven of the fourteen Northern California historical
NIFC–MTBS research candidates have **multiple** CAL FIRE name-linked incident
pages. Replaying all genuine original government source bytes, they compare
alternative page dates, reported source-point separations, repeated URL
references across cases and unresolved evidence requirements. They yield
JSON, formula-safe CSV and offline HTML for **human research only**, never
verified event IDs or independent wildfire negatives.

The [complete CAL FIRE candidate-detail investigation matrix](docs/calfire-2018-complete-incident-matrix.md)
extends the four-detail-page pilot to the entire original set of 18
name-linked historical incident pages using bounded, non-overlapping
batches of six original CAL FIRE URLs. Full SHA-256 source replay is
required before exporting original event, date, county and location
comparisons as private JSON, formula-safe CSV and offline HTML. All
relations remain **retrospective research leads**, not validated same
fires, independent no-fire events or forecast quality measures.

The [original CAL FIRE incident detail-page research](docs/calfire-2018-original-incident-pages.md)
now follows a bounded, reproducible set of actual 2018 event URLs from the
source-verified annual archive. It preserves original full HTML source bytes,
SHA-256 and the historical title/day/acreage/county/location fields, flags
disagreement with archive metadata and offers retrospective proximity context
to MTBS centroids and NIFC polygons. Source point location is **not** proven
ignition geometry; linked government pages still do not provide independent
same-event confirmation or wildfire-negative labels.

The [live official CAL FIRE 2018 incident archive cross-reference](docs/calfire-2018-incident-source-crosswalk.md)
now archives the state's original historical incident-page HTML with exact
SHA-256 and compares retrospective incident names, dates, counties and acreage
with source-verified NIFC/MTBS geographic candidates. CAL FIRE event-page
links are preserved; name/day overlap is **only an external research lead**,
not confirmed event identity, independent provider validation or an
absence-of-fire label. The state archive is not geographically exhaustive and
can share upstream incident records with NIFC and MTBS.

The [private third-party incident evidence dossiers](docs/mtbs-independent-event-evidence.md)
now create a case-by-case *empty* verification checklist from actual NIFC–MTBS
research candidates. Researchers can privately archive original external incident
documents by exact SHA-256, bind their declared source identities, original
incident record IDs and dates to a genuine candidate, and audit two distinct
reviewers' HTTPS citations, publication/capture chronology and declared upstream
lineages. The publicly tested real 2018 source pipeline publishes **only the
empty checklist**, not invented external source documents or reviewer votes.
Even two structurally complete declared sources are **not authenticated
independent event identity or nonfire labels**.

The [source-verified MTBS–NIFC research work triage](docs/mtbs-candidate-research-triage.md)
now produces deterministic coordinator JSON, formula-safe CSV and static HTML
priorities from the original government source records, region source-ID
population, candidate multiplicity, MTBS fire type and descriptive name tokens.
It can optionally incorporate **genuine separate reviewer disagreements**
through the existing double-review verification, without synthesizing opinions
in CI. Priority represents **manual investigation workload**, never a
quantitative same-event likelihood, negative wildfire label or prediction score.

The [two-reviewer MTBS–NIFC reconciliation](docs/mtbs-nifc-pair-reconciliation.md)
compares distinct private human reviews of the same source-verified candidate
set, reports agreeing *hypotheses*, conflicting opinions, inconclusive cases,
repeated source citations, and many-to-many geographic candidates. Read-only
local HTML and JSON retain each reviewer decision and original review-file
SHA-256 without promoting **any** pair into an independently verified fire
event, nonfire control, or forecasting metric.

The [offline MTBS–NIFC pair review workbench](docs/mtbs-nifc-pair-review.md)
lets researchers review authentic same-region source proximity pairs with
original government names, MTBS fire type, polygon/centroid SVG previews,
and evidence-backed **unverified hypotheses**. It independently rechecks
original source response bytes, region ObjectID population/selection hashes,
record geometries and *all* candidate pairs before making a CSP-restricted,
standalone HTML reviewer packet, and validates downloaded hypothesis JSON.
Nothing enters the binary wildfire/nonfire label pipeline without separate
independent adjudication and coverage evidence.

The [same-region MTBS/NIFC historical investigation](docs/mtbs-nifc-shared-region-study.md)
now queries both genuine government datasets for **the same bounded WGS84 region
and the same year** before sampling, preserves original provider response bytes,
source-ID population/selection digests, and geographic candidate pairs for
manual investigation. Nearness is not verified event identity; MTBS includes
prescribed burns and both data sources have different coverage limits.

The [real USGS/USFS MTBS second-source pilot](docs/mtbs-second-source-pilot.md)
adds a different official *post-fire large-fire mapping* source. It samples
2017/2018 year-specific USDA ArcGIS fire-centroid layers with reproducible
source IDs, preserves exact source bytes and date/fire-type metadata, and
optionally compares geographic co-location with archived NIFC perimeters.
MTBS includes prescribed burns, uses size/imagery thresholds and may share
upstream records with NIFC: **it is not a complete wildfire census, verified
negative data or proof of independently validated model accuracy**.

The [multi-year official NIFC study](docs/official-multiyear-nifc-study.md)
now retrieves deterministic, seeded-hash samples of independently published
historical US perimeter records across several years, preserving the official
ObjectID population digests, sampled ID hashes, original polygons, real capture
times, per-year source counts and explicit collection completeness warnings.
GitHub CI can verify a bounded **real** two-year source sample and retain its
research SQLite/GeoJSON evidence. This is a source-record study, not national
wildfire incidence estimation, valid fire-negative labeling or a trained model.

An additional [live NIFC provider contract probe](docs/nifc-live-source-contract.md)
validates the official ArcGIS layer's current schema and queries exactly one
real historical polygon, archiving source hashes, source metadata and actual
retrieval timestamps for an independent CI integration check. This explicit
bounded read-only test is distinct from mocked offline regression fixtures.
It does **not** provide valid fire-negative labels or a global forecast.

An opt-in [official US historical perimeter evidence importer](docs/official-historical-perimeters.md)
now retrieves bounded, year-specific NIFC IFPH GeoJSON directly from the public
read-only ArcGIS source. The research SQLite archive versions source attributes
and polygon geometries by actual capture time; the offline CLI produces
location-filtered JSON and GeoJSON reports. This source only covers retrospective
US fire perimeters through 2019, can omit fires, and **never provides automatic
negative labels or contemporaneous prediction features**.

The opt-in daily FIRMS research Releases can now be **verified and imported to a
persistent local SQLite pixel archive** via
[`fire_public.pixel_history`](docs/global-firms-pixel-archive.md). It validates
asset checksums and raw-source record provenance, supports idempotent,
transactional multi-release imports, and produces geodesic worldwide
historical source-coverage reports with the map's 0.05°/UTC-hour grouping.
This is an **offline** research workflow requiring downloaded release assets,
not continuous free cloud storage or validated wildfire event history.
Downloaded pixel data and SQLite databases must remain outside this public repo.

A bounded [official USFS MTBS reference downloader](docs/mtbs-reference-acquisition.md)
can now acquire complete, small, year/bounding-box filtered wildfire GeoJSON
cohorts directly from the USFS ArcGIS FeatureServer. It stores a SHA-256
provenance manifest, and the retrospective benchmark accepts it via
`--reference-manifest` without manually re-entering publisher and retrieval
time. Requests fail closed on incomplete pagination, unexpected source results
or oversized datasets. **These are post-fire references, never live inputs.**
MTBS historical fire dates and the project's newer research FIRMS archive may
not yet overlap, so no real detection scores have been established.

A separate [retrospective MTBS perimeter benchmark](docs/retrospective-perimeter-benchmark.md)
now compares an explicitly supplied official-schema burned-area GeoJSON
reference with historical, checksum-verified raw FIRMS pixel records.
The offline CLI preserves source file hashes and observation/capture dates,
handles antimeridian polygons, classifies missing collector receipts and
excludes prescribed burns. Final perimeters are **post-event reference
geometry**, never prediction inputs, and unmatched polygons are not non-fire
labels. Importantly, current research Release assets may be **too recent**
to overlap published MTBS historical fires. No actual detection accuracy
has been measured by the bundled synthetic-fixture tests.

The [regional source coverage audit](docs/global-source-coverage-audit.md) is integrated
into that explorer. It compares the selected circle's NASA FIRMS candidate observations
and NIFC/CWFIS current agency records with the snapshot's per-source health,
acquisition age and known scope. US NWS and perimeters are explicitly listed as
on-demand/not monitored sources rather than implied global coverage. The panel
also exports an auditable JSON snapshot with provenance and missingness warnings.
It is a client-side evidence tool: **zero detections never prove absence of fire,
and a successful world API call does not validate regional observation completeness.**

The **global region explorer** lets users select an arbitrary point on the map
or use the current center, choose a 25/50/100/250 km radius and see candidate
cell-hours, distinct cells, repeated UTC observations, a six-bin time chart,
source memberships and up to five inspectable locations within the existing
6/24/72-hour filter. It works across the international date line and keeps
the selected region in the shareable URL. It reuses the *current* public
snapshot in the browser: no extra FIRMS queries, KV writes, location tracking
or claim of globally validated wildfire probabilities. Counts can be incomplete
when providers are stale or failed; a chart is **observation activity**, not
fire growth or burned area. Choose **Use map center** or **Choose on map**
in the sidebar, then inspect the resulting region panel.

The preview also lists up to five recently observed cells in the visible map area.
Cells observed in multiple UTC hours appear first; selecting one centers the map
and opens its underlying observation. This is an investigation queue, not a danger
ranking or fire confirmation. Source failures and stale data are shown beside it.
The [observation investigation slice](docs/analysis-product-2026-10-12.md)
is only an early step toward the [wildfire analysis product objective](docs/wildfire-analysis-product-vision-2026-10-12.md).

Agency incident details can show the first observation here and up to four latest
source record changes. It is not a fire perimeter or spread history; an
unavailable source never proves that a fire ended. The separate
[four-question analysis panel](docs/wildfire-analysis-product-vision-2026-10-12.md)
states what the selected agency record or satellite candidate supports and why
ignition, spread, and ending probabilities are still unavailable. The separate
[historical evidence pilot](docs/historical-evidence-pilot-2026-10-12.md)
stores a small official US/Canada sample with capture times and checksum-verified
raw responses for later model research. This pilot is local and does not add a
long-term collector or fire predictions.

For a selected US NIFC incident, the draft preview can show [NWS grid forecast
context](docs/us-weather-context-pilot-2026-10-12.md): wind, gust, temperature,
humidity, forecast precipitation intervals, and 6/12/24-hour condition changes
at the recorded point. The browser
requests this only when an incident is opened. It is not a weather observation at
the fire or a fire-spread prediction. A separate one-point local archive pilot
checks forecast receipt times and offline replay; the browser requests are not
archived model inputs. Canada and Türkiye do not yet have weather context.
For an exact-ID US NIFC incident, the draft preview can also show a bounded
[agency mapped perimeter](docs/us-perimeter-context-pilot-2026-10-12.md) directly
from WFIGS, with its source date and a warning when old. It is a reported past
boundary, not the current burning area or a future spread forecast. Missing
perimeters remain unknown; no perimeter history is collected by the map.

The local [decision-time evidence audit](docs/decision-time-evidence-audit-2026-10-12.md)
reads an explicitly selected agency event and NWS forecast from separate SQLite
archives. It excludes late receipts, distant weather points, and forecast values
that do not cover the decision time. It does not create training labels or a model.
The local [CWFIS status time-series pilot](docs/agency-status-series-2026-10-12.md)
reports source-status intervals, gaps, corrections, and an under-control to
out-of-control reversal without turning those records into extinguishment labels.
An opt-in [prospective agency receipt pilot](docs/prospective-agency-receipts-2026-10-12.md)
can create bounded GitHub Actions artifacts from successful collector snapshots
at four UTC hours per day. It is disabled until `ENABLE_ANALYSIS_ARCHIVE=true` is
set after integration; 90-day artifacts are temporary research evidence, not a
durable training archive.
Downloaded receipts can be imported into a local SQLite research archive with
`python -m fire_public.receipt_history --receipts DIR --db /path/outside/repo/history.sqlite3`.
As-of queries keep source outages and missing listings separate from a fire outcome.

NASA FIRMS requires a free MAP_KEY. See <https://firms.modaps.eosdis.nasa.gov/api/area/>.
NIFC data comes from the [WFIGS current incident layer](https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations_Current/FeatureServer/0).
Canadian records come from the [CWFIS current active fire layer](https://cwfis.cfs.nrcan.gc.ca/downloads/docs/en/references/cwfif/cwfis-data-placemat.pdf)
and use the [Open Government Licence — Canada](https://cwfis.cfs.nrcan.gc.ca/downloads/licence.txt).
Attribution: Canadian Forest Service, Canadian Wildland Fire Information System
(CWFIS), Natural Resources Canada, Northern Forestry Centre, Edmonton, Alberta.
Map tiles use [OpenFreeMap Liberty](https://openfreemap.org/quick_start/).
The [Europe plus Türkiye source inventory](docs/europe-official-source-inventory.csv)
currently lists all 52 M49 areas in scope. Its official feeds remain under review;
satellite candidates are the only current European coverage. This blocks a stable
release claim. The [EFFIS shared-source audit](docs/europe-shared-source-audit-2026-10-10.md)
explains why its FIRMS-derived active-fire layer cannot count as an independent
agency incident feed. The [MTG publication audit](docs/mtg-publication-audit-2026-10-10.md)
records the source rights and runtime checks still needed before public MTG
collection can be enabled.

## Zero-charge deployment gate

Deployment requires a verified Cloudflare Workers **Free** account and only Pages
static hosting, Pages Functions, and Workers KV Free. Do not enable Workers Paid,
R2, paid add-ons, or larger GitHub runners. The collector reads account subscriptions
before each KV write and rejects paid or unknown plans. KV Free quota exhaustion
causes a failed collection or stale map, not an automatic upgrade. Use a dedicated
API token with Billing Read and KV Storage Write, plus `FIRMS_MAP_KEY`.
For a new account whose subscriptions API returns an empty first page, the gate
also requires an account-specific dashboard Free-plan attestation in
`CLOUDFLARE_FREE_ATTESTED_ACCOUNT_ID`. This value must match
`CLOUDFLARE_ACCOUNT_ID`; a paid subscription is always rejected.

The GitHub workflow is scheduled at :17 and :47 UTC each hour. A separate
Cloudflare Workers Free Cron Trigger checks the KV pointer at :05, :20, :35,
and :50. It dispatches the same GitHub workflow without forcing collection
only when the latest verified scan is at least 65 minutes old. A one-hour KV
dispatch marker usually limits repeated requests if GitHub is slow; KV's
eventual consistency can still permit an extra request. The Worker has no
public HTTP route and does not download FIRMS data or publish snapshots.
A run skips provider
downloads and KV writes if the last successful scan is under 55 minutes old.
If the public snapshot cannot be read, scheduled runs use the current KV pointer's
last scan time. An empty namespace can seed itself, and an expired snapshot can
be replaced on the next scheduled run. If both timestamps are unverifiable,
scheduled runs skip until readback recovers or an operator manually dispatches
a repair run. Pointers written before this timestamp field was added also need
one manual repair run if their public snapshot is already unreadable. Manual
dispatch bypasses this cadence guard, so repeated
manual runs can exhaust the Free storage quota and leave the map stale; they do
not activate a paid plan. Each immutable snapshot is gzip
compressed, capped at 5 MiB and expires in seven days; the current pointer is
read before provider downloads and written last. A failed pointer read aborts
the run; a missing pointer is accepted only after its KV namespace is verified.
If Pages serves an older or malformed cached snapshot, the valid pointer time controls
the cadence guard. A malformed pointer timestamp stops publication. With successful
timestamp reads and no repeated manual overrides,
even a maximum-size snapshot every 55 minutes stays below the 1 GB Free storage
ceiling for seven days. [GitHub may delay or drop scheduled
events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows),
so successful jobs alone do not prove continuous coverage. The independent
Cron Trigger reduces dependence on GitHub's scheduler but still requires live
observation; its own failure or an expired GitHub token can stop the backup.
The first 72-hour source-only probe produced a 3.20 MB gzip snapshot; a later
live run published about 149,000 candidates. A larger future source response or
snapshot can hit the fail-closed limits and leave the prior version stale.
Uncached map requests make two KV reads, or three while an older version is used
during KV propagation. The 10,000 visits/day target implies 20,000–30,000
reads/day, below the current 100,000/day Free limit. This is a design
budget, pending load and real-data measurements. Public Actions standard runners
are free for public repositories.

The site requires a Pages project named `wildfire-signals`, with repository root
as project root, `public/` as build output, and a sibling `functions/` directory.
The checked-in `wrangler.toml` supplies the `PUBLIC_SNAPSHOTS` KV binding.
`/api/*` is the only Function route.
Set repository variables `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_KV_NAMESPACE_ID`,
and `PUBLIC_SNAPSHOT_URL`; set repository secrets `FIRMS_MAP_KEY` and
`CLOUDFLARE_API_TOKEN`.

### Free backup scheduler deployment

The scheduler is a separate Worker in `scheduler-worker/`; it does not replace
the Pages project. [Workers Free](https://developers.cloudflare.com/workers/platform/pricing/)
allows 100,000 requests/day, and the [Free account has five Cron Trigger
slots](https://developers.cloudflare.com/workers/platform/limits/). This
project uses one trigger (96 scheduled invocations/day). With a healthy map it
reads one small KV pointer per invocation; when stale it also reads a dispatch
marker and can write one marker per successful GitHub dispatch. Each scheduled
invocation also writes a small `scheduler:tick:<UTC time>` receipt with an
eight-day TTL (at most 96 extra writes/day). These receipts show whether Cron
ran even when a fresh snapshot correctly suppresses a GitHub run. Free quota
exhaustion fails rather than activating paid usage. Confirm a Cron slot is
available in the Cloudflare account before deployment; no paid plan is needed.

Create two repository [Actions secrets](https://github.com/frogiraffe/wildfire-signals/settings/secrets/actions)
without posting their values in issues or chat:

1. `SCHEDULER_GITHUB_TOKEN`: a [fine-grained GitHub token](https://github.com/settings/personal-access-tokens/new)
   limited to `frogiraffe/wildfire-signals`, with repository **Actions: Read and
   write** only. The Worker receives it as an encrypted secret. Record its
   expiration and renew it before expiry.
2. `CLOUDFLARE_WORKERS_DEPLOY_TOKEN`: a [Cloudflare API token](https://dash.cloudflare.com/profile/api-tokens)
   limited to this account, with Workers Scripts Edit/new Worker deployment
   permission. Do not grant Billing Edit or R2 permissions. The existing
   Cloudflare token separately verifies the Free subscription before deployment.

Run the [Deploy Free backup scheduler workflow](https://github.com/frogiraffe/wildfire-signals/actions/workflows/deploy-scheduler.yml)
manually from `main`. It tests the Worker, checks the Free gate, and deploys
`wildfire-signals-scheduler` with no public route and a 15-minute Cron Trigger.
If the account lacks its free, account-wide `workers.dev` subdomain, the deploy
workflow creates `wildfire-signals-<account-id>.workers.dev` first. It preserves
an existing subdomain and keeps this Worker's public `workers.dev` route disabled.
The token values remain GitHub/Cloudflare secrets. Check the Cloudflare Worker
Cron execution history and the GitHub collect workflow's dispatch runs. A
manual collect run defaults to forced repair; the Worker explicitly passes
`force_collection=false`, so the collector's 55-minute guard remains active.
Deployment success alone does not prove a Cron invocation or a fresh snapshot.

To connect the account without pasting a token into chat:

1. In the [Cloudflare dashboard](https://dash.cloudflare.com/), confirm the
   account uses Workers Free. Keep the free `pages.dev` address and decline paid
   products or upgrades.
2. Create a narrowly scoped [API token](https://dash.cloudflare.com/profile/api-tokens)
   for that account with **Billing Read** and **Workers KV Storage Edit**. Store it
   as the repository's `CLOUDFLARE_API_TOKEN` Actions **secret**. Copy the
   [Account ID](https://developers.cloudflare.com/fundamentals/account/find-account-and-zone-ids/)
   (32 hexadecimal characters) into the `CLOUDFLARE_ACCOUNT_ID` Actions
   **variable**. An API token is never an Actions variable. If one was placed
   there, delete it and revoke it in Cloudflare before creating a replacement.
3. Run the manual `Verify Cloudflare Free account` GitHub Actions workflow. It
   only reads subscription information. If Cloudflare returns no subscriptions,
   first confirm Workers & Pages shows **Free** with no paid add-ons, then set
   `CLOUDFLARE_FREE_ATTESTED_ACCOUNT_ID` to the same Account ID. A paid, unknown
   or unverifiable response fails closed and creates no resource.
4. Connect this repository to Cloudflare Pages as project `wildfire-signals`,
   with repository root `/`, no build command and output directory `public`.
   The classic KV namespace has already been created and its binding is in
   `wrangler.toml`; confirm it appears in the deployed Pages project. Set the
   actual `https://<project>.pages.dev/api/snapshot` URL as a repository variable.
5. The Free check, initial snapshot size and live endpoint have been checked.
   `ENABLE_PUBLIC_COLLECTION=true` is enabled for hosted hourly collection;
   the developer's computer need not stay on. Each run repeats the Free gate.

The source-only pilot was disabled after the live hosted collector succeeded,
avoiding duplicate FIRMS requests. Observe the live preview for seven days from
10 October 2026, checking gaps, source freshness, Free quotas, browser behavior
and real traffic before a 1.0/stable release claim.

The manual `Check live map in browser` GitHub workflow checks desktop and mobile
Chromium against the public preview. It checks loaded data, source state, map
canvas, the 72-hour filter and horizontal fit; visual quality and real device
interaction still need review.

## Private agency evidence recovery (experimental)

GitHub Actions source receipts expire; the live map's KV snapshots are not a
durable training/evidence archive. To keep prospectively captured NIFC/CWFIS
agency source bytes locally before expiry, use the **read-only**
[GitHub Actions recovery sync](docs/github-actions-agency-recovery-sync.md),
which verifies the official collector run and imports only exact source receipts
into the [private original evidence vault](docs/durable-agency-evidence-vault.md).
A fine-grained GitHub credential with **Actions: read** is required; no token is
checked in or printed.

```sh
# From outside the Git checkout; source data and vault stay private.
python -m fire_public.actions_agency_sync --vault /private/wildfire-vault --dry-run
python -m fire_public.actions_agency_sync --vault /private/wildfire-vault
python -m fire_public.agency_vault workspace \
  --vault /private/wildfire-vault --provider cwfis \
  --output-dir /private/source-research-001
```

Repeated sync invocations remember already checked immutable artifact IDs and
progress through older receipts; they do **not** automatically schedule backup or
recover already expired ZIPs. Confirm that real agency receipts actually exist,
then export an independent vault ZIP backup to another physical storage location.
An agency source record, or its presence/absence in a source layer, is **not**
independent physical wildfire validation, a negative label, or extinguishment.

## Historical statistical Analysis Engine v2

The worldwide map includes the real-time **Analysis Engine v1** with six-bin
descriptive thermal signal statistics. A second, fully reproducible
[historical statistical analysis engine](docs/historical-statistical-analysis-v2.md)
now works directly from previously verified **original NASA FIRMS pixel
research releases** held in a local SQLite history index. It distinguishes
original satellite acquisition time from first captured archive receipt time,
groups independent 0.05° / UTC-hour thermal candidates, audits collector
availability per source, and computes a descriptive robust trend **only when
each UTC time bin has completed source receipts**.

```sh
python -m fire_public.historical_signal_analysis \
  --pixel-db /private/wildfire-research/pixels.sqlite3 \
  --at 2026-10-13T00:00:00Z --hours 72 \
  --latitude 36.9 --longitude 30.7 --radius-km 100 \
  --json /private/wildfire-research/antalya-stats.json \
  --html /private/wildfire-research/antalya-stats.html
```

Alternatively, run the [manual historical FIRMS statistical analysis workflow](.github/workflows/run-historical-signal-analysis.yml)
from the GitHub Actions tab. It fetches available public research releases,
validates their original source receipts, generates real-data reports for a
selected global circle, and retains **only** an aggregate HTML/JSON analysis
artifact for seven days. It is manual only; no recurring job or raw government
incident uploads are configured.

It produces a portable local-source JSON + HTML research report, not a
commercial fire forecast. Collector receipt counts **do not** measure satellite
overpass or cloud-free acquisition opportunities; source completeness is an
audit of what can be analyzed, not proof of no fire. Ignition probability,
physical wildfire severity/spread and validated predictive scores remain
explicitly unavailable.

## Analysis Engine v3 — historical multi-region study frame

The [source-censored historical observation cohort](docs/observational-study-cohort-v3.md)
generates repeated, as-of `(region_id, decision_at)` observational rows from
original validated FIRMS pixels. Declare non-overlapping worldwide circles,
fixed UTC decisions and a future target horizon. The output is R/Python-ready
`observations.csv` plus full source-bound JSONL, SHA256 manifest and an offline
quality dashboard. Missing/incomplete collection periods yield **null numeric
features** rather than invented zeros. Even complete collector requests are
not verified satellite overpass opportunities.

```sh
python -m fire_public.observational_cohort \
  --pixel-db /private/firms-pixels.sqlite3 \
  --regions-json examples/observational-regions.json \
  --start-at 2026-10-12T00:00:00Z --end-at 2026-10-13T00:00:00Z \
  --cadence-hours 6 --lookback-hours 24 --target-hours 24 \
  --output-dir /private/firms-study-20261013
```

**Every target remains null and model fitting is blocked** until licensed,
independently established fire and nonfire outcomes plus source availability
are audited. The existing
[manual real-data analysis workflow](.github/workflows/run-historical-signal-analysis.yml)
now includes the source-censored study frame as an extra aggregate-only output
without publishing raw agency events or satellite pixels.

## Local checks

```sh
python -m unittest discover -s tests -v
node --test tests/js/*.test.mjs
```

Review missing and failed scheduled collection intervals using GitHub's workflow
run history. The earlier source pilot audit covers only its own fixed window and
does not make a release decision on its own:

```sh
gh run list --workflow source-pilot.yml --limit 200 \
  --json createdAt,status,conclusion,event,databaseId > pilot-runs.json
python -m fire_public.pilot_audit pilot-runs.json
```
