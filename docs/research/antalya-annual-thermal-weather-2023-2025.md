# Antalya standard FIRMS archive and station weather, 2023–2025

**Status:** retrospective, exploratory observation analysis. These results count archived thermal candidates. They do not estimate fire occurrence, weather effects, burned area, fire risk, or a forecast.

## Question and sources

Can three full calendar years of original standard-processing VIIRS detections be joined reproducibly to real station weather, while preserving the distinction between an archived detection and an observed no-detection? The study circle is 25 km around Antalya airport (36.8987° N, 30.8005° E). Selection of this region and station followed inspection of accessible sources; it is not a representative sample.

The six original [NASA FIRMS country CSVs](https://firms2.modaps.eosdis.nasa.gov/download/) cover 2023–2025 for NOAA-20 and Suomi NPP, Collection 2 standard processing. [VIIRS attribute documentation](https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_VIIRS_Firehotspots.html) describes acquisition time, confidence and classification. A documented historical `type` classification defect means the file's `type=0` must not be interpreted as an independently verified vegetation fire. [NASA data use policy](https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy) applies; the report redistributes bounded aggregates and source references, not the large original archive. Source URL, byte size, SHA-256 and HTTP Last-Modified are pinned in [the manifest](../../examples/antalya-annual-manifest-2023-2025.json).

The three original [NOAA NCEI GHCNh station-year PSV files](https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly) are for station `TUI0000LTAI` in 2023–2025. [GHCNh documentation](https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/doc/ghcnh_DOCUMENTATION.pdf) defines source-specific quality codes. Code `1` for source `223` is passed quality, not a failure; variable wind direction `999` is undefined, not 999°. [NOAA metadata and rights](https://www.ncei.noaa.gov/access/metadata/landing-page/bin/iso?id=gov.noaa.ncdc%3AC01688) identify CC0-1.0. The files were revised in 2026; an HTTP revision timestamp does not establish each hourly observation's first availability. This is retrospective context, never a historical forecast input.

## Method and population

The builder verifies all nine raw file byte counts and SHA-256 hashes before processing. It streams country CSV rows, checks provider/year/version and acquisition time, and deduplicates exact records within each source file using temporary on-disk SQLite. It selects source pixels inside the 25 km great-circle radius and aggregates by provider, UTC day/month, and 0.05° cell × UTC hour. Pixels from different sensors are not silently merged. The public JSON contains no individual pixel coordinates. Weather uses the latest *earlier or equal* station record no more than 60 minutes before the first candidate minute in each sensor-hour. No interpolation or later weather observation is used. This is one fixed station, not pixel-scale meteorology. Monthly weather medians use all available station records in each month, separate from the positive-only satellite subset.

| Measure | Real result | Denominator and meaning |
|---|---:|---|
| Country CSV rows read | 257,907 | Six source files; all Turkey rows, not six complete acquisition histories |
| Exact same-file duplicate rows | 0 | Exact source-row identity only |
| Selected raw pixels | 1,340 | 25 km Antalya circle, both sensors, 2023–2025 |
| Positive sensor × UTC-hour groups | 994 | An hour enters only if at least one selected pixel exists |
| UTC days with at least one archived candidate | 617 | Days without records are **unknown**, not negative days |
| NOAA station rows | 62,230 | Three station-year files; source records are not independent days |
| Positive sensor-hours with earlier temperature | 988 / 994 | Six lack a qualifying earlier value within 60 minutes |
| Positive sensor-hours with earlier humidity | 986 / 994 | Eight lack a qualifying earlier value |
| Positive sensor-hours with earlier wind speed | 988 / 994 | Six lack a qualifying earlier value |
| Positive sensor-hours with defined wind direction | 940 / 994 | Variable/calm direction and unavailable records remain null |

| UTC year | NOAA-20 pixels | Suomi NPP pixels | Both sensors' pixels | Candidate cell-hours summed by sensor | Days with archived candidates | Positive sensor-hours |
|---|---:|---:|---:|---:|---:|---:|
| 2023 | 313 | 307 | 620 | 528 | 271 | 470 |
| 2024 | 258 | 250 | 508 | 423 | 238 | 378 |
| 2025 | 107 | 105 | 212 | 167 | 108 | 146 |

The largest month in the selected archive is October 2023 with 98 raw pixels across both sensors; June 2024 has 84. These are source counts, not rates, and monthly zero rows mean no selected *archived* detections in those files. Among the **988 positive sensor-hours** with a prior station temperature, the median is 22.0 °C (range 2.0–42.0 °C); median wind speed is 3.1 m/s (n=988), and median humidity is 64% (n=986). These values describe weather associated with **selection into the positive archive subset**, not a temperature effect or the distribution of conditions during every satellite opportunity. Serially close station measurements and clustered pixels are not independent samples. No correlation, regression coefficient, confidence interval, trend significance, or seasonality inference is reported.

The lower 2025 count could reflect real thermal activity, acquisition coverage, cloud/quality effects, archive processing or other collection changes. No independent swath/quality denominator was joined. The country files' successful download does not establish observation opportunity at this circle. No independently verified wildfire outcome exists for these rows. Accordingly neither occurrence nor spread modeling is eligible. The original source file availability at each historical decision time is unknown; these revised files must not be used to claim a backtested real-time prediction.

## Reproduce and inspect

Download each of the nine URLs listed in the manifest into one local directory **outside Git**, using the listed filenames. Recheck SHA-256 against the manifest, then run:

```sh
python -m fire_public.annual_country_analytics \
  --manifest examples/antalya-annual-manifest-2023-2025.json \
  --raw-dir /private/antalya-annual-raw \
  --output /private/antalya-annual-replay.json
sha256sum /private/antalya-annual-replay.json \
  public/data/antalya-annual-context-2023-2025.json
```

The verified local replay matched the [published analytical JSON](../../public/data/antalya-annual-context-2023-2025.json) byte for byte: SHA-256 `3c9c95e5b524178241f13d0834fb699eed645db21b53f211b10c0dd3163c4091`. The 20,441,459-byte NASA inputs and 47,415,198-byte NOAA inputs remain outside Git. The static joined report is 529,006 bytes, loaded only on the analytics page; no collector, Workers KV, paid service or new secret is involved. Its 994 positive groups and 36 station-month medians are intentionally bounded; large source files are streamed or held one station-year at a time. A changed upstream file fails the pinned hash and requires a new reviewed manifest/report, never silent overwrite.

One local Python 3.14 run of the final builder over all nine pinned files took **4.473 s**, with **54,928 KiB peak process RSS** (`resource.getrusage`); the input contained 257,907 FIRMS rows. This is a single local measurement, not a runner or Cloudflare throughput guarantee. The original source population fits the explicit 50 MiB-per-file and 100,000-selected-pixel budgets. A larger region or file needs a reviewed bounded processing strategy rather than lifting those guards without measurement.

## Next evidence gate

Obtain sensor swath/acquisition and quality evidence for the *same* 2023–2025 region/time units before deriving a no-detection denominator. Obtain independent event evidence, source availability times and prespecified temporal/geographic holdouts before a fire occurrence model or statistical weather-effect claim. The existing paired CMR catalog audit is metadata only and cannot fill this gap.
