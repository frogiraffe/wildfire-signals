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

The preview also lists up to five recently observed cells in the visible map area.
Cells observed in multiple UTC hours appear first; selecting one centers the map
and opens its underlying observation. This is an investigation queue, not a danger
ranking or fire confirmation. Source failures and stale data are shown beside it.
The [observation investigation slice](docs/analysis-product-2026-10-12.md)
is only an early step toward the [wildfire analysis product objective](docs/wildfire-analysis-product-vision-2026-10-12.md).

Agency incident details can show the first observation here and up to four latest
source record changes. It is not a fire perimeter or spread history; an
unavailable source never proves that a fire ended. The separate
[historical evidence pilot](docs/historical-evidence-pilot-2026-10-12.md)
stores a small official US/Canada sample with capture times and checksum-verified
raw responses for later model research. This pilot is local and does not add a
long-term collector or fire predictions.

For a selected US NIFC incident, the draft preview can show [NWS grid forecast
context](docs/us-weather-context-pilot-2026-10-12.md): wind, gust, temperature,
humidity, and forecast precipitation intervals at the recorded point. The browser
requests this only when an incident is opened. It is not a weather observation at
the fire, fire-spread prediction, or archived model input; Canada and Türkiye do
not yet have weather context.

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
