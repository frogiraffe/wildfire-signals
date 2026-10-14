# Standard VIIRS catalog and wildfire model readiness: Antalya, 6–7 January 2025

**Status:** bounded, exploratory source audit. No independent wildfire outcome, negative observation, calibrated model, or fire forecast was produced.

## Question and study unit

Can standard NOAA-20 VIIRS L1 geolocation and L2 active-fire products supply the missing observation and outcome evidence for the three-year Antalya FIRMS study? The bounded unit here is a **NOAA-20 UTC date in a 25 km study circle**, with original archived FIRMS candidate minutes retained separately. A NASA CMR search box (`30.5,36.6,31.1,37.2` WGS84) encloses the circle but is not the circle or a pixel coverage mask. These two dates were chosen to contrast one archived candidate minute with a following day without an archived candidate; they were not sampled for fire-rate estimation.

## Sources and rights

- [NASA FIRMS standard VIIRS country archive](https://firms2.modaps.eosdis.nasa.gov/download/): the existing [Antalya annual evidence report](../../public/data/antalya-annual-context-2023-2025.json), SHA-256 `a2b2b583167e12459b2f68e470b029310c4437610d6e6746c998de63e931f9e4`, pins six original 2023–2025 NOAA-20/S-NPP CSVs. The country source population is 257,907 rows; 1,340 original pixels are inside the Antalya circle over three years. This audit selects only NOAA-20 records on the two dates.
- [NASA CMR public granule metadata](https://cmr.earthdata.nasa.gov/search/): original two-query [snapshot](source-samples/antalya-standard-cmr-2025-01-06-07.json), 50,965 bytes, file SHA-256 `3afd0613dda847d2ccaf8cbab90413485ea5a5c77ed274a7ec94c8df44438889`, captured 2026-10-14 15:52:16 UTC. `VJ103IMG` L1 geolocation version `2.1` is catalogued by LAADS; `VJ114IMG` L2 active fire uses **version `002`** in LPCLOUD. A version `2` CMR query returned zero hits; treating this metadata spelling as no product would be a query error. The original response hashes are `010d9cd0692faa019bcf4bc4400028459cd0550b0ad0d04bbabc2ec798ffb5ea` (L1) and `d27b538f06b51053c82369072986e14ad22a453ab92a2aa64b76228961576a56` (L2). The snapshot preserves exact query URLs, hit counts and raw response bodies.
- The [NASA Earthdata data-use policy](https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy) applies. This repository publishes bounded metadata and aggregates, not protected granule contents.

## Method and genuine numerical result

The offline builder verifies the annual report hash, both original CMR response hashes, exact product/version/query contract, CMR hit counts, collection provider identity, UTC intervals and search footprints. It pairs L1/L2 records on exact NOAA-20 six-minute intervals and checks whether the archived positive minute falls inside a pair. It never converts catalog search polygons into a cell swath.

| UTC date | Paired L1/L2 catalog intervals starting that date | Archived NOAA-20 raw pixels in circle | Evidence state |
|---|---:|---:|---|
| 2025-01-06 | 4 | 1, at 00:17 UTC | Archived thermal candidate; physical cause unresolved |
| 2025-01-07 | 2 | 0 | No archived record; satellite opportunity unknown |

The 00:17 positive minute falls in the 00:12–00:18 UTC paired catalog interval. Across both dates, **6 L1 entries, 6 L2 entries and 6 exact pairs** were catalogued. These are granule metadata counts, not observations of the study circle. No no-detection population is calculated. The 7 January zero is an archive count and must not become a negative label.

## Acquisition and independent outcome audit

Bounded anonymous HTTP range requests to one L1 LAADS granule and one L2 LPDAAC granule redirected to Earthdata Login and returned **401** on 2026-10-14. No already authorized Earthdata credentials were available. Thus original geolocation arrays, per-pixel acquisition, cloud/quality flags and L2 fire-mask categories were **not inspected**. A catalog entry or orbit estimate cannot establish a valid observation of a 0.05° cell. File availability, first publication time and product revisions cannot be inferred from CMR `updated` timestamps alone.

[EFFIS Rapid Damage Assessment methods](https://forest-fire.emergency.copernicus.eu/about-effis/technical-background/rapid-damage-assessment) use satellite burned-area mapping but also MODIS/VIIRS active-fire information as ancillary evidence, and the mapped population omits some small fires. Its [historical data service](https://forest-fire.emergency.copernicus.eu/applications/data-and-services) requires a data request for some historical extracts. Therefore an EFFIS polygon cannot automatically be called an independent physical-event label for this FIRMS cohort; source lineage and date/location coverage would need review. The [Turkish forestry agency annual report](https://www.ogm.gov.tr/tr/e-kutuphane-sitesi/FaaliyetRaporu/2025%20-%20Orman%20Genel%20M%C3%BCd%C3%BCrl%C3%BC%C4%9F%C3%BC%20Faaliyet%20Raporu.pdf) reports national annual totals, which do not establish geolocated daily positives and covered negatives for this observation unit.

## Model decision

The reproducible [machine-readable audit](../../public/data/antalya-standard-granule-readiness-2025-01-06-07.json) records separate failed gates for outcome and horizon definition, cell-level exposure, independent positives, independent negatives, decision-time environmental availability, and separated temporal/geographic evaluation. Scientific model comparison and operational prediction are **ineligible**. Models trained: **0**. Existing collection-output experiments remain distinct from wildfire occurrence.

## Reproduce and costs

```sh
python -m fire_public.standard_granule_readiness \
  --snapshot docs/research/source-samples/antalya-standard-cmr-2025-01-06-07.json \
  --annual public/data/antalya-annual-context-2023-2025.json \
  --output /tmp/antalya-standard-replay.json
sha256sum /tmp/antalya-standard-replay.json
```

Expected output file SHA-256: `6a945e8bcfb0400c67e1954925cfa0c4f69155e3d99188e1b2b68dd2b107b884`. Measured local replay: **0.057 s**, peak child RSS **28,772 KiB**; one run, Python 3.14, including process startup. The public aggregate is **4,150 bytes** and the pinned source snapshot is **50,965 bytes**. Replays are offline and need no API, Worker KV, account or paid resource. This measurement is not a cloud performance guarantee.

**Next evidence step:** obtain authorized L1/L2 granule content access, then verify swath intersections, invalid/cloud pixels and complete fire-mask coverage for predefined cells; separately obtain independently reviewed dated/geolocated event and observation coverage evidence. Only after that define a prospective occurrence target and a separated evaluation cohort.
