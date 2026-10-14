# Dalaman standard FIRMS archive and station weather, 2023–2025

**Status:** retrospective descriptive pilot in a second region. No wildfire event, regional fire rate, environmental effect or forecast was validated.

## Region choice and original evidence

Dalaman airport was selected **before reading its thermal counts**. The [official NOAA GHCNh station list](https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/doc/ghcnh-station-list.csv), SHA-256 `812ea50bd5efd1b9cc09d5800c55825b3d43b1bfaaef`, identifies `TUI0000LTBS` at 36.7131° N, 28.7925° E, elevation 6.1 m. It is a geographically distinct southwestern Türkiye coastal station from Antalya airport. Its official 2023, 2024 and 2025 station-year files were all available. A fixed 25 km circle centered on that station was declared, matching the Antalya design. This selection tests geographic reuse with the *same* NASA source files and period, avoiding a post hoc search for high fire counts. It does not make the two sites representative of Türkiye.

The six original [NASA FIRMS standard VIIRS Turkey country CSVs](https://firms2.modaps.eosdis.nasa.gov/download/) are the **same SHA-256-pinned 2023–2025 files** used in the [Antalya report](antalya-annual-thermal-weather-2023-2025.md), for NOAA-20 and Suomi NPP. The [Dalaman manifest](../../examples/dalaman-annual-manifest-2023-2025.json) pins all nine original URLs, byte sizes, hashes and HTTP Last-Modified times. The new NOAA GHCNh Dalaman station-year SHA-256 values are `0e2a5ae1bb96ff28bbb9b831efe183c4f1f9f8500c83faee187937c273e3b15d` (2023), `29d6d285f08c3e5c68e89c4e582e1497334e2c3e80d54a43dfc1388d07e800ef` (2024), and `c66a9c5f2beafacde1ceb5131028591765b5a8a0f284ba340b526a5671505509` (2025). NOAA files were revised on 2026-07-11. Original availability at each historical decision time remains unknown.

[GHCNh documentation](https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/doc/ghcnh_DOCUMENTATION.pdf) governs source-specific quality codes and units; [NOAA metadata](https://www.ncei.noaa.gov/access/metadata/landing-page/bin/iso?id=gov.noaa.ncdc%3AC01688) identify CC0-1.0. NASA's [VIIRS attributes](https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_VIIRS_Firehotspots.html) and [data use policy](https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy) apply. The historical `type` classification defect prevents treating `type=0` as verified vegetation fire. No NOAA-21 rows were added without a separately verified source contract.

## Method, numerical results and missingness

The same bounded [annual builder](../../fire_public/annual_country_analytics.py) verifies every source hash, streams all country records, deduplicates exact within-file rows on temporary SQLite, selects original pixel coordinates by great-circle distance, and groups UTC date/month and 0.05° cell × hour **separately for each sensor**. A positive sensor-hour joins only the latest earlier or simultaneous station observation within 60 minutes of its first candidate minute. Station values are point measurements, not pixel weather; interpolation is not performed. Monthly station medians use all source station observations in the month, separate from the selected positive thermal groups.

| Measure | Result | Denominator |
|---|---:|---|
| FIRMS source records read | 257,907 | Six Turkey country CSVs, shared with Antalya |
| Exact same-file duplicates | 0 | Exact original row identity, not physical event identity |
| Selected raw thermal pixels | 79 | 25 km Dalaman circle, 2023–2025, both sensors |
| Positive sensor × UTC-hour groups | 38 | Only hours with an archived selected pixel enter |
| UTC dates with archived candidates | 27 | Unlisted dates are unknown, not observed negatives |
| Station source records | 61,539 | Three GHCNh Dalaman station-year files |
| Positive sensor-hours matched to prior temperature, wind and humidity | 38 / 38 | Does not describe weather availability at no-detection hours |
| Positive sensor-hours with defined wind direction | 37 / 38 | Calm/variable or missing direction is null |

| UTC year | NOAA-20 pixels | S-NPP pixels | Both sensors' pixels | Candidate cell-hours summed by sensor | Dates with candidates | Positive sensor-hours | Prior temperature matches |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023 | 3 | 5 | 8 | 8 | 8 | 8 | 8 |
| 2024 | 11 | 7 | 18 | 15 | 10 | 15 | 15 |
| 2025 | 23 | 30 | 53 | 18 | 9 | 15 | 15 |

Among the **38 positive sensor-hours**, median prior station temperature is 24.5 °C, median wind speed 5.7 m/s and median humidity 46%. These are outcome-selected hours with serial, seasonal and source dependence. The 2025 archive has 53 pixels in only 18 candidate cell-hours and nine dates, making spatial or temporal concentration worth investigating. It does **not** establish one fire, a larger burned area, a static industrial source, or an increasing fire trend. No confidence interval, correlation coefficient or weather-effect regression is justified from the positive-only sample. Source acquisition opportunity, cloud/quality coverage, independent outcome status and decision-time availability remain unknown. The web comparison therefore presents counts and missingness but no fire-rate ranking.

## Reproduce and operational cost

Download the three Dalaman NOAA files named in the manifest outside Git. Reuse the six already verified NASA country files from the Antalya study in the same raw directory. Then run:

```sh
python -m fire_public.annual_country_analytics \
  --manifest examples/dalaman-annual-manifest-2023-2025.json \
  --raw-dir /private/turkey-annual-raw \
  --output /private/dalaman-annual-replay.json
sha256sum /private/dalaman-annual-replay.json \
  public/data/dalaman-annual-context-2023-2025.json
```

The authentic nine-file replay was byte-identical to the [published aggregate](../../public/data/dalaman-annual-context-2023-2025.json), SHA-256 `813b888d16bb4c5952999f3955cf23ca19cc4cdf391192df22cb64eeac812ec5`. Antalya's published aggregate separately retained its SHA-256 `3c9c95e5b524178241f13d0834fb699eed645db21b53f211b10c0dd3163c4091`. One local Python 3.14 processing run took 4.812 s, 52,652 KiB peak process RSS, over 257,907 country records. The new NOAA files total 45,949,029 bytes outside Git; the public aggregate is 48,003 bytes. The UI uses static reports with no KV write, scheduled collector, secret or paid service. These are single local measurements, not guarantees of hosted throughput.

## Scientific next step

The two reports supply enough authentic geolocated records for a **descriptive** recurrence audit. Repeated cells should be marked as repeated observations, not automatically industrial sites; NASA's [Static Thermal Anomalies Mask](https://firms.modaps.eosdis.nasa.gov/descriptions/Static_Thermal_Anomalies_Mask.html) is reference material and explicitly unavailable for redistribution. Independently documented swath/quality and wildfire outcome evidence are still required before a fire occurrence cohort or model can be claimed.
