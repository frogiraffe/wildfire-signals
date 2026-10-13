# Analysis Engine v2 — historical FIRMS statistics with source collection quality

The project now provides two complementary statistical analyses:

- **Live map Analysis Engine v1:** descriptive six-bin statistics from one currently public 72-hour snapshot, on a world map
- **Historical Analysis Engine v2:** reproduces a source-censored longitudinal analysis of verified original NASA FIRMS pixel receipts, indexed in local SQLite, at a specified *decision time* and geographic circle

The second is an independent **offline historical research report**, not a new cloud archive, probability service or deployment. It uses the existing `pixel_history.import_release_assets` importer. Historical releases must genuinely exist, be downloaded and verify successfully. See [reproducible global FIRMS pixel archive](global-firms-pixel-archive.md) and [research release sync](research-release-sync.md).

## Reproduce the analysis

Use the exact original release asset sets to build the existing read-only analysis input:

```sh
# Download previously published NASA FIRMS opt-in research release assets.
python -m fire_public.release_sync --help
python -m fire_public.pixel_history import \
  --assets /private/wildfire-research/releases \
  --db /private/wildfire-research/pixels.sqlite3

# Run actual historical statistical analysis for a worldwide location.
python -m fire_public.historical_signal_analysis \
  --pixel-db /private/wildfire-research/pixels.sqlite3 \
  --at 2026-10-13T00:00:00Z --hours 72 \
  --latitude 36.9 --longitude 30.7 --radius-km 100 \
  --json /private/wildfire-research/antalya-statistics.json \
  --html /private/wildfire-research/antalya-statistics.html
```

Open the new HTML file locally. It contains no external scripts, CDNs, model calls or network requests. JSON includes original archived scan receipt SHA-256 references, audit counts, source status, source-filtered pixel aggregations and detailed bins. Existing output files and the SQLite input cannot be overwritten. `--source VIIRS_NOAA20_NRT` (or `VIIRS_NOAA21_NRT`) selects a single original satellite source. Omit for both.

Supported window lengths are 24, 48, 72, 168 and 336 hours, all partitioned into **12 equal, UTC-bounded bins**. All circles are geodesic with radius up to 250 km, including areas straddling the 180° meridian.

## Two distinct clocks, not one surrogate timestamp

- **Observed at:** the pixel's raw FIRMS acquisition time; this determines the statistical bin
- **First captured at:** the earliest verified archived receipt in which the original pixel was encountered; this determines *whether the pixel may be known at the chosen decision cutoff*
- **Scan at and captured at:** original collection attempt and archive receipt times; the user can inspect their source health by time bin

A pixel whose observed timestamp predates the cutoff but whose earliest receipt **postdates** it is excluded. Backfilled data therefore cannot leak backwards into an earlier analysis. The report counts archived raw detections independently of the 0.05-degree geodesic cell × UTC-hour rollup, and separately exposes delayed first captures.

Each of 12 bins shows: distinct observed candidate cell-hours, distinct cells, raw pixel detections, pixels first captured in that bin, later-bin captures of older observations, source cell-hour memberships, collection receipt counts, and per-source `complete`/`failed`/`deferred` counts.

## Statistical quantities and conditions

| Measure | Interpretation |
| --- | --- |
| Unique raw detections | Source-originated FIRMS pixels known at decision time in selected place/window |
| Distinct candidate cell-hours | One 0.05-degree cell and one UTC hour, regardless of repeated raw source pixels |
| Multi-sensor cell-hours | Cell/hour co-membership of original NOAA-20 and NOAA-21 sources; **not** independent fire validation |
| Median first-capture delay | Lag from pixel acquisition to earliest archived receipt, not original NASA publication latency |
| Twelve-bin median and MAD | Descriptive central tendency and dispersion of 0.05° cell-hour counts |
| Theil–Sen slope | Median pairwise bin count slopes in **candidate cell-hours/hour** |
| Later minus earlier and ratio | Difference / ratio between two six-bin halves; ratio unavailable if denominator zero |

**Important gate:** Theil–Sen, median/MAD and half-window comparisons are `null` unless every one of the twelve time bins has at least **one completed collection receipt from every selected source**. This prevents treating evident ingestion outages and missing receipts as zero-valued time-series bins. Raw counts are still shown as a description of available source evidence, alongside gaps and scan status.

This is a *necessary*, not sufficient, condition for interpreting a trend. Completed GitHub collection runs are **not** verified VIIRS orbit passes or cloud-free observation opportunities. Collection source completeness is not observational coverage. No satellite revisit exposure or land denominator is fabricated, so even a successful trend is **not** an increase in physical wildfire activity or an exposure-adjusted fire-incidence estimate. No p-values, model accuracy, wildfire ignition probabilities or spread forecasts are generated.

## Reproducibility, safety, and limits

- The importer already validates original raw source-field digests, source rights, timestamps and scan receipt manifests. The v2 engine operates on that verified local SQLite; the input is opened **read-only**.
- Scan and pixel queries enforce decision-time source availability, source type, geographic circle, and exact half-open UTC windows. Query limits are 10,000 original scans and 250,000 unique raw pixel records. Over-budget analyses fail rather than silently truncate.
- Source receipt SHA-256 hashes are present for the first 128 scans in chronological order; the count of remaining scans is reported, and a digest of the complete chronological list is provided.
- The report has no verified non-fire examples, independently established wildfire outcomes, weather covariates or satellite overpass denominators. Absence of detections is never treated as evidence of no wildfire.
- Output should be inspected as experimental *statistical descriptive research*, not a wildfire early warning or validated predictive model.

## Tests

```sh
python -m unittest discover -s tests -p 'test_historical_signal_analysis.py' -v
python -m unittest discover -s tests -p 'test_pixel_history.py' -v
```

Tests exercise 12 actual synthetic original source receipts with rising counts; source failures; missing bins; exact decision time and delayed captures; distinct source membership; 180° longitude wrap; and HTML/JSON new-only CLI. These are **reproducibility tests** and do not constitute performance on actual historical wildfire cases.
