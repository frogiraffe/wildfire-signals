# Spatial recurrence and source-quality audit, Antalya and Dalaman, 2023–2025

**Status:** genuine, positive-only descriptive research. Repeated thermal detections are not independent wildfire events, confirmed industrial sources, burned area, or valid no-detection evidence.

## Research question and source contract

How concentrated are the 2023–2025 archived NASA FIRMS detections in the two already selected 25 km circles, and how much of an apparent year difference depends on recurring cells and FIRMS source types? The [Antalya](antalya-annual-thermal-weather-2023-2025.md) and [Dalaman](dalaman-annual-thermal-weather-2023-2025.md) studies define the geography before this audit. The module uses the **same six original standard-processing VIIRS Turkey country CSVs**, source hashes and provider/year identities from the [Antalya manifest](../../examples/antalya-annual-manifest-2023-2025.json). It streams all 257,907 original rows, checks SHA-256 and source revision metadata, and deduplicates exact source rows on temporary disk SQLite. The original files remain outside Git.

[NASA's VIIRS attribute documentation](https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_VIIRS_Firehotspots.html) defines nominal 375 m fire pixel centers, low/nominal/high confidence, day/night, UTC acquisition and source-inferred type values. Source type `2` is an inferred other static land source; type `0` is a presumed vegetation fire. [NASA documents a historical Collection 2 type defect](https://firms.modaps.eosdis.nasa.gov/descriptions/Static_Thermal_Anomalies_Mask.html) under which some obvious type-2 detections were recorded as type 0. Neither value is independent ground truth. [NASA's Static Thermal Anomalies Mask](https://firms.modaps.eosdis.nasa.gov/descriptions/Static_Thermal_Anomalies_Mask.html) uses broader multi-source analysis and is **not available for distribution**; its contents were not copied, queried as a label, or joined to this report. [NASA data-use guidance](https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy) applies to the original detections.

## Method and evidence classes

Original pixel coordinates are assigned to 0.01° WGS84 bins. This is an **analysis grid**, roughly kilometre-scale at these latitudes, not a VIIRS footprint, an event identity, or a fixed physical source boundary. Exact original coordinates remain outside Git; the public output contains only bounded grid aggregates. For each bin the builder records raw pixel count, distinct UTC observation dates/years, first/last acquisition, same-day presence of both sensors, day/night and confidence counts, FIRMS type counts, and maximum one-date share. Same-day two-sensor presence is co-observation, not independent physical-event verification. The reports publish at most 20 bins per region with two or more pixels; all other bins enter only region totals.

The descriptive label `recurrently_observed_candidate` means **at least two archived UTC dates in one bin**. The separate `potential_static_thermal_source` review cue requires at least 12 dates, at least two years, and FIRMS source type 2 on at least half of that bin's pixels. These are transparent pilot triage thresholds, **not validated universal diagnostic cutoffs**. Every bin retains `source_identity_status=unresolved` and `independently_classified=false`. No bin receives `independently_classified_non_vegetation_source` or `independently_verified_wildfire_event`: no independent reference evidence exists here. Absence of detections in another bin is unknown acquisition opportunity, not a negative observation.

## Actual numerical findings

| Region | Selected raw pixels | Occupied 0.01° bins | Bins on ≥2 dates | Bins in ≥2 years | Bins with same-day both-sensor presence | Potential-static review bins |
|---|---:|---:|---:|---:|---:|---:|
| Antalya 25 km | 1,340 | 248 | 65 | 43 | 33 | 2 |
| Dalaman 25 km | 79 | 34 | 4 | 3 | 10 | 0 |

Antalya's leading bin contains **748/1,340 pixels (55.82%)**, observed on **477 distinct UTC dates across three years**, with 741 source type-2 and seven source type-0 records. A neighbouring bin contains **139 pixels**, 116 dates across three years, with 128 type-2 records. Together these two bins account for **887/1,340 (66.19%)** of selected Antalya pixels. These aggregates show pronounced spatial persistence in the *archive*. They neither prove one industrial source nor show that all type-0 pixels elsewhere are wildfires. Dalaman's largest bin has nine pixels; its most date-persistent bin has five pixels on five dates across two years. Neither meets the pilot potential-static cue.

| Region and UTC year | All archived pixels | FIRMS type 0 | FIRMS type 2 | FIRMS type 3 | Day / night | Low / nominal / high confidence |
|---|---:|---:|---:|---:|---:|---:|
| Antalya 2023 | 620 | 140 | 480 | 0 | 166 / 454 | 17 / 602 / 1 |
| Antalya 2024 | 508 | 168 | 340 | 0 | 172 / 336 | 37 / 458 / 13 |
| Antalya 2025 | 212 | 163 | 49 | 0 | 129 / 83 | 23 / 188 / 1 |
| Dalaman 2023 | 8 | 8 | 0 | 0 | 5 / 3 | 1 / 7 / 0 |
| Dalaman 2024 | 18 | 18 | 0 | 0 | 12 / 6 | 2 / 16 / 0 |
| Dalaman 2025 | 53 | 50 | 0 | 3 | 42 / 11 | 4 / 49 / 0 |

**The Antalya aggregate decline (620 → 212 pixels) is dominated numerically by source type-2 records changing from 480 to 49.** Type-0 counts are 140, 168 and 163. This does not establish a stable wildfire signal: NASA's type field has known defects, acquisitions/cloud/quality and archive revisions are not controlled, and neither class has independently reviewed event labels. No trend test, regional fire-rate ratio, environmental association or predictive model is warranted. The sharp concentration also means treating 1,340 pixels as independent samples would badly understate spatial dependence.

## Reproduction, size and remaining gates

With the six original files from the Antalya manifest outside Git:

```sh
python -m fire_public.spatial_recurrence \
  --manifest examples/antalya-annual-manifest-2023-2025.json \
  --regions-json examples/annual-spatial-regions-2023-2025.json \
  --raw-dir /private/turkey-annual-raw \
  --output /private/turkey-spatial-replay.json
sha256sum /private/turkey-spatial-replay.json \
  public/data/turkey-spatial-recurrence-2023-2025.json
```

The real-source replay was byte-identical to the [published aggregate](../../public/data/turkey-spatial-recurrence-2023-2025.json), SHA-256 `4a5336988792217d77e788cc6a2fc61df4536c7e7a52d69669232cc0112e96da`. The static JSON is 29,431 bytes. A single local Python 3.14 run over all 257,907 source rows took **3.649 s** and **31,708 KiB peak RSS**; this is local evidence, not a cloud throughput guarantee. The code bounds selected pixels, region count and published bins. No new collector, KV write, paid service, secret or raw archive in Git is introduced.

The next scientific gate is independent and licensed reference evidence for actual static sites and physical wildfire outcomes, plus VIIRS swath/fire-mask quality for the same cells and times. NASA CMR catalog presence alone does not verify cell exposure. These requirements remain open; the current output supports only descriptive source-quality and spatial-concentration investigation.
