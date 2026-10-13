# Analytics and scientific modeling roadmap

Status: 2026-10-13 research preview. This document records code and the bounded real-data pilot on branch `codex/real-analytics-baseline-20261013`; it does not promote any wildfire model to validated status. The broader product direction remains in [the product vision](wildfire-analysis-product-vision-2026-10-12.md) and [engineering policy](ENGINEERING_POLICY.md).

## Current capability and gap analysis

`Completed` means implemented with local tests; `Experimental` means a real-data research pilot without scientific validation. An open PR is not a deployed capability.

| Capability | Status | Current evidence and gap |
|---|---|---|
| NASA FIRMS VIIRS NOAA-20/21 collection and candidate grouping | Completed | `collect.py`, `pixel_history.py`, collector and archive tests; candidates remain distinct from fires. |
| MTG and LSA SAF ingestion | Missing | No implementation in this public checkout. Do not copy private project data or code. |
| NIFC/CWFIS current and prospective agency receipts | Completed | `collect.py`, `agency_history.py`, `agency_cohort_review.py`; not independent wildfire ground truth. |
| CAL FIRE/MTBS/NIFC event research | Experimental | Source-specific archive, ambiguity, lineage and review modules exist; pilot links are not verified physical event identity. |
| SQLite pixel and agency history, SHA-256 source receipts | Completed | `pixel_history.py`, `history.py`, `evidence_receipts.py` and associated tests. |
| Multi-scan daily research release sync | Completed in this branch | `release_sync.py` now verifies each same-day scan and its own pixel files; real two-release import and offline replay exercised. |
| Historical Intelligence Workbench / Change Explorer | Partial | Offline investigation reports exist, but general public historical queries and incident timelines are not yet available in the web app. |
| Independent label review and negative coverage gate | Partial | Code enforces source review, independent evidence and censored negatives; a globally adequate independently labeled cohort has not been established. |
| Temporal availability and evaluation splits | Completed as methods | `temporal_evidence.py`, `evaluation_splits.py`, `observational_cohort.py` and tests; applied fire forecast evaluation remains blocked by labels. |
| Live regional descriptive statistics | Completed | `public/analysis-engine.mjs` and map panel operate on recent public snapshots; they cannot infer fire counts. |
| Original-pixel historical statistics | Completed | `historical_signal_analysis.py` computes receipt-aware local reports. |
| Global multi-region original-pixel aggregate and web pilot | Experimental | This branch adds `thermal_capture_analytics.py`, a fixed 12-region aggregate, and `analytics.html`. Archive is short and spatial sample exploratory. |
| Next-scan collection-count persistence / log-linear experiment | Experimental | Time/geography split implemented. Real training target has zero variation; model comparison is **unsupported**. No fire prediction skill is reported. |
| Weather, land cover, fuels, topography associations | Missing | Existing weather context is a live point forecast, not a versioned historical multi-region analysis dataset. |
| Independently validated occurrence, spread, containment forecasting | Blocked | Independent positive/negative labels, verified observation opportunities, event identity, adequate temporal/geographic test samples and calibration evidence are absent. |

## Data adequacy and first real pilot

The input is two public research releases (`analysis-evidence-2026-10-12`, `analysis-evidence-2026-10-13`) from the project's own original NASA FIRMS archive. The repaired importer verified **5 scan receipts**, **10 original pixel assets**, source SHA-256 hashes and row provenance. Across the two releases, 1,351,891 pixel rows were read; 994,444 were repeated by source record identity, leaving **357,447 unique original raw pixels** in SQLite. The 12 fixed, nonoverlapping 250 km circles contain **26,205 unique raw pixels**; 331,242 lie outside. Observed UTC dates run **2026-10-09 through 2026-10-13**, but the first scan is a rolling 72-hour bootstrap, and no day has proven continuous satellite acquisition. The regions are an exploratory selection, not a random or representative worldwide sample.

The first capture scans are at 2026-10-12 18:19, 2026-10-13 00:20, 06:35, 12:50 and 18:50 UTC. Selected-region *new* candidate cell-hour counts per scan are **7,194, 447, 0, 0, 1,329** respectively. The middle zeros describe no *newly archived* selected candidates, not no fire, no satellite anomaly, or no satellite overpass. Source query receipts are complete for both VIIRS sources in these scans; overpass/exposure coverage is unverified. Annual and seasonal comparisons, a prevalence denominator, incident outcomes, environment correlations and fire-rate trends are unavailable.

The experiment's target is next scan's newly archived candidate cell-hour count in a selected circle. It skips the bootstrap transition, trains a one-lag persistence baseline and log1p single-feature OLS on **20 earlier region transitions**, and reserves **10 later temporal**, **4 earlier geographic**, and **2 joint temporal/geographic** transitions. Australia North and Brazil Amazon are geographic holdouts. Training targets contain one value (zero): fitted intercept and slope are both zero. On the temporal holdout, persistence MAE = **131.8** and log-linear MAE = **131.8** candidate cell-hours; on the joint holdout both MAEs = **5.5** (n=2). Geographic holdout MAEs are 68.0 and 0.0 respectively (n=4), but a constant-zero fit and sparse acquisitions make the apparent improvement meaningless. **No model beats the baseline with supportable scientific evidence.** There are no uncertainty intervals or calibrated fire probabilities. This is executable research plumbing, not a usable forecast.

The compact aggregate report is [the fixed pilot JSON](../public/data/thermal-capture-pilot-2026-10-13.json) (about 32 KiB), with report SHA-256 `5bb8fd54881e31a3788a83cc6b6f85e8bda07c56fc4698d792a9b6a57a9799ef`. Raw pixels and SQLite remain outside Git. Local research transfer used about 129 MB compressed release assets and 240 MB SQLite; neither enters Workers KV or Cloudflare. Web reads one static JSON file, with no new service, secret or paid quota.

## Data contract and reproducibility

| Field | Meaning | Availability/limitation |
|---|---|---|
| `observed_at` | Original UTC FIRMS acquisition | Original source row; not ignition time. |
| `first_captured_at`, `first_scan_at` | First local collector receipt and source scan | Must be after observation; used to prevent later data entering earlier transitions. |
| `receipt_sha256`, asset hashes | Source evidence and exact archived bytes | Validated during import/sync. |
| `source_states` | Collector request outcome per sensor | `complete` does not verify overpass or cloud-free visibility. |
| `new_raw_pixels` | Unique original source records first captured by a scan | Sensor duplicates remain distinct raw records. |
| `new_candidate_cell_hours` | Distinct 0.05° WGS84 cell × observed UTC hour first captured by a scan/region | Both sensors in the same cell-hour count once; not fire count, area, or severity. |
| `daily_rows`, `weekly_rows`, `monthly_rows` | Descriptive sums by original observation time | Every period is flagged `archive_period_complete=false`; missing dates are not zero-filled. |
| `rolling_3_observed_days` | Three-day mean only for contiguous listed UTC dates | Descriptive only; daily coverage is incomplete. |
| Environment variables, agency outcomes | Not included in this pilot | Unit, spatial/time resolution, publication/issue time, availability and missingness contracts must precede integration. |

Reproduce from already downloaded, verified public research releases (no secret needed after download):

```sh
python -m fire_public.release_sync \
  --assets-dir /private/firms-releases --db /private/firms-pixels.sqlite3 \
  --since 2026-10-12 --max-releases 2 --max-total-mb 160 \
  --hours 72 --coverage-json /private/sync-evidence.json
python -m fire_public.thermal_capture_analytics \
  --pixel-db /private/firms-pixels.sqlite3 \
  --regions-json examples/thermal-capture-regions.json \
  --holdout-region AUSTRALIA_NORTH --holdout-region BRAZIL_AMAZON \
  --output-json /private/thermal-pilot.json
```

The CLI refuses to overwrite an existing report and does not make a network request. Public GitHub releases can change or expire; a later rerun must compare the report hash, receipt hashes, source versions and record counts before interpreting any numerical difference. No random seed is needed for deterministic one-feature OLS. The model uses Python standard library only; no ML package or runtime is added to the public app.

## Prioritized executable backlog

| Track | Priority | Status | Objective | Existing components | Deliverable and acceptance | Dependency |
|---|---|---|---|---|---|---|
| A | P0 | Partial | Show provider reliability and regional coverage in the live map | Coverage audit, map panel, open PR #56 | Review PR #56 CI and deploy only with authorization; missing/failed sources visibly distinct | Production approval |
| B | P0 | Experimental | Expose real original-pixel history | SQLite, release sync, statistical analysis, this aggregate/UI | Archive pilot loads in desktop/mobile browser, shows partial days and source provenance; expand only with durable bounded storage | Repeatable source archive |
| C | P0 | Experimental | Quantify a defensible first statistical target | This persistence/log-linear research pipeline | Continue capture-count baseline only when several weeks of nondegenerate six-hour receipts exist; predefine regions and split before the next analysis | B and acquisition exposure audit |
| D | P1 | Missing | Historical environmental context in one real region | Weather context and decision evidence | Source/license/time contract, real joined report with missingness | Versioned historical environment source |
| E | P1 | Missing | ML comparison where it could add value | Split and evaluation modules | Only if C has nondegenerate samples; beat simple baseline on temporal and geographic tests with intervals | C |
| F | P1 | Partial | Independent scientific evaluation | Label review, receipts, negative coverage gate | Two-reviewer positive/negative cohort and verified observation opportunity; leakage audit | Independent rights-compatible labels |
| G | P1 | Partial | Interactive analytics workspace | Existing map and new fixed pilot page | Broaden date/region selection from bounded historical query service with coverage gating | B, privacy/cost review |
| H | P2 | Blocked | Validated forecasting | Historical baseline, evaluation modules | Calibration and independent target-specific validation plus operational release gate | F, C/E, sustained data |

## Release and decision gates

Research preview permits descriptive archived observations and explicitly experimental collection-output experiments. A validated fire model needs a preregistered target/horizon, separately evidenced positives and negatives, verified acquisition exposure, two-reviewer adjudication, frozen source versions, temporal/geographic/event holdouts, baseline comparison, uncertainty, calibration and prospective monitoring. None has passed for this pilot. The public page therefore shows descriptive counts and research method, with no fire probability or operational prediction layer.

Next large vertical slice: accumulate a longer original-source archive outside Git; add measured satellite acquisition opportunity and first historical environmental variable in one licensed region. Re-run the same frozen region/split protocol only after capture targets vary and acquisition gaps are accounted for. Preserve a separate independent fire-label evaluation track.
