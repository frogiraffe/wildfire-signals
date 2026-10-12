# MTBS second actual official fire-assessment source (2017–2018 pilot)

The USDA Forest Service and USGS **Monitoring Trends in Burn Severity** project (MTBS) is a *different* official retrospective mapping program from the NIFC Interagency Fire Perimeter History source already archived by Wildfire Signals. This bounded real-data integration focuses on the USDA ArcGIS REST **Fire Occurrence Locations** yearly point layers and compares sampled geographic context with the current sampled NIFC perimeter archive. The event records have common government upstream information and are NOT automatically statistically independent ground-truth labels.

## Source metadata, rights and limits

Official publisher USFS/USGS, fixed HTTPS ArcGIS MapServer: `https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MTBS_01/MapServer`.

- Year **2017: layer 68** (Fire Occurrence Locations).
- Year **2018: layer 70** (Fire Occurrence Locations).
- General country coverage: United States mainland, Alaska, Hawai'i and Puerto Rico; geographic coverage does not imply completeness.
- MTBS includes inventoried **large** fires, including wildfires and prescribed fires. Mapping thresholds are roughly **1,000 acres in western USA and 500 acres in eastern USA**, so small fires must not be counted as negatives. Some other large fires cannot be mapped due to unusable imagery or mapping/agency records.
- The original mapped occurrence points represent mapped burned-area centroids and are NOT guaranteed wildfire ignition locations or independently verified ignition times. These records were mapped after the event and were not known as they appear at the original decision time.
- Data.gov published source catalog and USFS ArcGIS publication metadata identify the dataset and license. Users should acknowledge MTBS, USGS and USFS and obey source-specific attribution requirements.
- This program may have used some of the same incident inputs as NIFC. Therefore even agreement across sources is only a research *co-location candidate*, never independent outcome proof.

Sources:
- https://catalog.data.gov/dataset/monitoring-trends-in-burn-severity-fire-occurrence-locations-feature-layer
- https://www.mtbs.gov/faq/fire-mapping
- https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MTBS_01/MapServer/62

## Bounded live source capture

```bash
python -m fire_public.mtbs_pilot \
  --year 2017 --year 2018 \
  --records-per-year 4 \
  --seed mtbs-research-v1 \
  --output-dir /private/wildfire/mtbs-2017-2018
```

Optionally compare against independently already downloaded NIFC historical polygons:

```bash
python -m fire_public.mtbs_pilot \
  --year 2017 --year 2018 \
  --records-per-year 4 \
  --seed mtbs-research-v1 \
  --nifc-db /private/wildfire/nifc-study.sqlite3 \
  --nifc-at 2026-10-13T18:00:00Z \
  --output-dir /private/wildfire/mtbs-nifc-comparison
```

The first command uses **six** bounded, read-only government REST GETs (one per-year layer metadata request, one per-year complete list of provider ObjectIDs, and one per-year selected attribute/point geometry request). The exact provider layer ID/name/field/geometry contract is checked. The maximum is two specific historical years and twenty points per year; an actual source ID list may be much larger than the selected sample. Stable SHA-256(seed,year,ObjectID) ranking selects an auditably reproducible subset of provider-published records. **This does not make it a probability sample of all US wildfires.**

The CLI preserves original provider API response bytes in six year/source-role JSON files, per-file SHA-256 and byte count, original source attributes converted into a bounded descriptive report, original reported acreage, fire type (including prescribed burns), source ignition-date attribute (where available) and the actual source capture time.

It refuses a missing original source ID, wrong layer, unexpected year, invalid coordinates, duplicate IDs, unexpected schema, excessive response size or existing destination directory. No paid resource, scheduled downloader, arbitrary HTTP URL or cloud storage is enabled. Sensitive research output belongs outside public GitHub.

## NIFC cross-source comparison

Optional NIFC comparison loads the SHA-verified archived NIFC 2017/2018 study and checks whether each MTBS mapped fire **centroid** is inside or within a configurable study radius (default 50 km) of any same-year NIFC mapped polygon. Output `nifc-proximity-candidates.json` contains ID pairs for **human spatial review only**; proximity does NOT establish common fire-event identity, MTBS/agency independence, fire growth or diagnostic skill. With two separately sampled tiny datasets, unmatched source samples mean **nothing** about true wildfire absence or source recall. In particular, denominator must not be mistaken for a full wildfire inventory.

MTBS `fire_type` should eventually be filtered or stratified by domain-specific human decisions before any wildfire-only research evaluation. This pilot preserves it without assuming every MTBS record represents a naturally ignited wildfire.

## Real CI verification

The existing [NIFC multi-year source research CI](../.github/workflows/test-perimeter-study.yml) now also executes a live source sample of MTBS year-2017 and year-2018 point layers, saves actual USDA response bytes and SHA hashes alongside genuine NIFC eight perimeters, and runs source-by-source proximity exploration with explicit non-outcome classifications.

`tests/test_mtbs_pilot.py` injects **synthetic provider-shaped HTTP responses** and checks schema drift, sampled point identity, date and coordinate bounds, incomplete pages, reproducibility, byte preservation, and NIFC comparison. Offline fixture test success alone is not live provider success. If actual API tests fail, retain failure status rather than substituting synthetic records.

**Current maturity:** official second-provider retrospective fire observation pilot only. No independent negative fire labels, representative US incidence census, global agency coverage, calibrated wildfire forecast or measured detection accuracy.
