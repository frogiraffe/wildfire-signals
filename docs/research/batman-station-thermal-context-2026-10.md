# Batman station and archived thermal candidates: retrospective pilot

**Status:** exploratory descriptive report, 2026-10-14. The [joined evidence JSON](../../public/data/batman-weather-context-2026-10-11.json) and [historical analytics page](../../public/analytics.html) are the reproducible outputs. This report does not estimate wildfire occurrence, environmental effects, or forecast skill.

## Question and selection

What conditions did one fixed weather station report near hours with archived NASA FIRMS thermal candidates? We searched actual GHCNh station locations against the existing short FIRMS archive. Antalya station TUI0000LTAI had only five raw pixels within 100 km during the weather overlap, none within 50 km. Batman station TUI0000LTCJ had 99 raw pixels within 25 km on 2026-10-10. We selected a 25 km Batman circle around 37.929° N, 41.1166° E for a bounded real-data implementation. **This selection used the outcomes being described.** It cannot support representative region comparisons, independent hypothesis tests, or causal claims.

## Original sources, rights and provenance

| Input | Evidence and rights | Time and spatial meaning |
|---|---|---|
| NASA FIRMS VIIRS NOAA-20/21 NRT original pixel assets | Five verified project research scan receipts; ten hashed original assets. [FIRMS](https://firms.modaps.eosdis.nasa.gov/) and [NASA data-use policy](https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy). The imported SQLite holds source record IDs, original row hashes, source URLs, rights URLs and first collector receipts. | Original acquisition UTC time and first archive capture time are separate. Candidate 0.05° cell-hours are not distinct fires, area or intensity. |
| NOAA NCEI GHCNh annual Batman PSV, station `TUI0000LTCJ` | [Official product page](https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly), [technical documentation](https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/doc/ghcnh_DOCUMENTATION.pdf), [2026 station file](https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/access/by-year/2026/psv/GHCNh_TUI0000LTCJ_2026.psv), [NOAA data-use guidance](https://www.noaa.gov/office-education/outreach-communication/faq). Downloaded source SHA-256: `1dcc60fcae10b9552f833169f7dc3284ac63a75398c24596a94d83397dbdf696`. Source HTTP Last-Modified: 2026-10-12 12:53:32 UTC. NOAA generally permits reuse of its data; inspect any third-party credit in derived station records before redistribution beyond this compact attribution-backed aggregate. | Fixed station at 37.929° N, 41.1166° E, 555.3 m. GHCNh source observations are UTC and can be revised. The file's revision time is **not** each observation's first availability time. This is retrospective context, not historical real-time forecast input. |

The raw NOAA file is about 13.9 MB and the original FIRMS archive/SQLite remain outside Git. The published joined aggregate is 22,171 bytes. It contains station hourly values, six candidate-hour aggregates, original source/receipt/asset hashes, units, observation-state vocabulary and explicit unmatched rows. It does not contain the full station file or raw satellite pixels.

## Method and observation units

The thermal observation unit is a distinct 0.05° WGS84 cell × acquisition UTC hour **first archived** in a verified scan. Multiple original source pixels may occupy one cell-hour. The weather unit is one irregular observation at a fixed station, with °C air temperature, m/s wind speed, wind direction in degrees and relative humidity in percent. We reject nonblank GHCNh quality-code values and invalid ranges; blank quality code means *unflagged in this file*, not independently certified. Wind direction is circular, so no arithmetic mean is reported. The file contains no precipitation readings in the selected window; we do not turn these blanks into zero rainfall.

For each candidate hour we join the latest station observation at or before that hour, within 60 minutes. This direction avoids using a later station measurement for the candidate hour, but **does not** prove the station record was published or accessible then. A fixed station is contextual for a 25 km circle, not a pixel-level meteorological measurement. Hours with no FIRMS candidate have unknown acquisition opportunity, not a zero outcome. No interpolation is performed. The collector's complete response is not an overpass record.

## Numerical findings

The 2026 file has 19,783 source rows through 2026-10-11 03:20 UTC. The selected 2026-10-09 to 2026-10-11 window contains 150 station rows: 150 temperature and humidity, 138 wind speed and 116 wind direction values; precipitation has no values. Across these 150 station rows, mean temperature is **17.467 °C** (range 8.0–27.4 °C), mean wind speed **1.259 m/s** among its 138 values (range 0–4.1 m/s), and mean relative humidity **65.86%** (range 21–100%). These are descriptive source-record statistics, not spatial averages.

The 25 km circle contains **125 original FIRMS pixels** in **56 distinct candidate cell-hours** across **six UTC acquisition hours**. Four candidate hours, all on 2026-10-10, match prior station temperature/humidity records. Three match wind speed and direction. Two candidate hours on 2026-10-11 have no station match because the available annual file ends at 03:20 UTC; their weather fields remain null. The four matched candidate-hour temperatures have median **24.7 °C**. Candidate cell-hours within the same hour share one station reading, so 56 cell-hours are **not 56 independent weather samples**. Daytime acquisition timing, land use, source detection bias and pilot selection can explain much of this apparent difference from the whole-window station mean. No correlation or regression is estimated.

The [web chart](../../public/analytics.html) shows the hourly station series and highlights archived candidate hours. Its blue bars for other hours must not be read as no fire or no thermal activity. The downloadable JSON exposes six hour-level joins and missingness for inspection.

## Validity and missing evidence

- No independent satellite overpass or footprint metadata have been joined. [NASA VNP03MOD NRT geolocation](https://www.earthdata.nasa.gov/data/catalog/lancemodis-vnp03mod-nrt-1) is a candidate source for a later bounded acquisition audit; the current archive cannot establish cloud-free cell-level opportunity from hotspots.
- No independent wildfire outcome labels, negative observations, event spread polygons or local fuel/topography measurements are in this pilot. The candidate target is observed/archive output, not confirmed incidence.
- The short October window cannot establish seasonality, weather associations, fire risk, or generalization to Antalya, Batman beyond these days, or the world.
- GHCNh is a retrospectively maintained archive. Although we use an earlier observation time in each join, the individual publication and first-availability times are unknown. Do not use these fields in an as-of forecasting evaluation.
- The first FIRMS scan bootstraps a rolling 72-hour window; scan cadence and deduplication affect new archive counts. Missing dates remain absent, never zero-filled.

## Reproduce offline

Use the already documented release-sync workflow in [the analytics roadmap](../ANALYTICS_MODELING_ROADMAP.md) to build a verified original-pixel SQLite DB outside Git. Download the official NOAA file at the exact source URL above and verify its SHA-256 before comparing the published numbers. Then run:

```sh
python -m fire_public.historical_rollup \
  --pixel-db /private/firms-pixels.sqlite3 \
  --regions-json examples/batman-station-pilot-region.json
python -m fire_public.environmental_analytics \
  --pixel-db /private/firms-pixels.sqlite3 \
  --regions-json examples/batman-station-pilot-region.json \
  --weather-psv /private/GHCNh_TUI0000LTCJ_2026.psv \
  --station-json examples/batman-ghcnh-station.json \
  --source-url https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/access/by-year/2026/psv/GHCNh_TUI0000LTCJ_2026.psv \
  --source-last-modified 2026-10-12T12:53:32+00:00 \
  --expected-weather-sha256 1dcc60fcae10b9552f833169f7dc3284ac63a75398c24596a94d83397dbdf696 \
  --start-date 2026-10-09 --end-date 2026-10-11 \
  --output-json /private/batman-weather-context.json
```

The exact published report digest is `0a8b3b4fe06cc97c7f3e4a5d7331acb26af5b197a08dd64a39d7b683c63b85b3`. If upstream station data are revised, a new SHA-256 and analysis version are required; do not overwrite the historical output silently.
