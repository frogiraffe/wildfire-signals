# Phase 4 evidence pilot: official perimeters and unresolved thermal recurrence

**Status:** reproducible retrospective research, 2026-10-15. These are two separate studies. The Sacramento agency perimeters are **not** matched to the Antalya/Dalaman FIRMS pixels and do not validate Turkish fires or a wildfire occurrence model.

## Questions and predefined study units

1. How much of the 2023–2025 Antalya/Dalaman **archived thermal-pixel** summary lies in the two previously flagged, physically unresolved recurrence bins? Unit: original NASA FIRMS VIIRS pixel; strata: region × UTC year × sensor.
2. What dated, geolocated non-FIRMS evidence is accessible in a fixed California pilot? The Sacramento box `[-121.88,38.45,-121.31,38.95]` WGS84 surrounds the **previously used Sacramento Metro Airport station**, not a selected fire cluster. Unit: CAL FIRE FRAP mapped final perimeter intersecting that box, source year 2023–2025. It is a box, not the station's earlier 25 km circle.

## Authentic sources, rights and provenance

| Source | Original population / bytes | Evidence contract |
|---|---:|---|
| [NASA FIRMS standard VIIRS Turkey country files](https://firms2.modaps.eosdis.nasa.gov/download/) | 6 original NOAA-20/S-NPP CSVs, 257,907 rows, approximately 20.4 MB | Exact asset URLs, bytes, SHA-256 and revisions in [Antalya source manifest](../../examples/antalya-annual-manifest-2023-2025.json). All six originals were downloaded again on 2026-10-15 and matched their pinned hashes. Original CSVs remain outside Git. [NASA data-use policy](https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy). |
| [Existing spatial recurrence evidence](../../public/data/turkey-spatial-recurrence-2023-2025.json) | 1,419 selected original pixels | SHA-256-verified input; 0.01° WGS84 bins are **research groups**, not sensor footprints or physical-source identities. NASA's [Static Thermal Anomalies Mask](https://firms.modaps.eosdis.nasa.gov/descriptions/Static_Thermal_Anomalies_Mask.html) is referenced, not redistributed or joined. |
| [CAL FIRE FRAP historic perimeter layer](https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/California_Historic_Fire_Perimeters/FeatureServer/0) | 9 GeoJSON polygons/multipolygons; original query response 54,048 bytes | Fixed 2023–2025 envelope query, original [GeoJSON](source-samples/sacramento-frap-2023-2025.geojson) SHA-256 `99ec874041ea1847fea4b14628be052ee1c5c4ab680ecc90e774cca7c015ae70`; separate [count response](source-samples/sacramento-frap-count-2023-2025.json) says 9, SHA-256 `77225c1b889e1a23d33f5e7724a89deba869a0b481aff9fe90736b56532d0542`; [layer metadata](source-samples/sacramento-frap-layer-metadata.json) SHA-256 `1ed42c91954cd7d4232a4862943bcab56f94d287b7ae773f18b6827f63333e04`. The layer calls its version `firep25_1` (April 2026). [State portal](https://publish.data.ca.gov/dataset/california-fire-perimeters-all) lists Creative Commons Attribution and public rights. Attribute and geometry corrections remain possible. |

The FRAP query uses `YEAR_ >= 2023 AND YEAR_ <= 2025`, `esriSpatialRelIntersects`, WGS84 input/output, a 100-row cap, and `OBJECTID ASC`. The server count of 9 matches the 9 downloaded features; no transfer-limit flag is present. The builder validates GlobalID uniqueness, dates, code domains, WGS84 coordinate bounds, and each feature's envelope overlap with the fixed query box. It does **not** reinterpret a final perimeter as an ignition location. The output retains original GlobalIDs, method/agency codes, dates and geometry bounds, while the pinned source sample retains original geometries.

## Thermal sensitivity: actual numerical result

All pixels remain in the primary total. The unresolved subset contains pixels inside the two original Antalya bins marked for *potential static-source review* by recurrence and source-type criteria. It is **not** an independently confirmed non-wildfire exclusion. No Dalaman bin met that particular review rule.

| Region / UTC year | All archived pixels | Unresolved recurrent-bin pixels | Other unverified candidates | FIRMS type-2 pixels in unresolved bins |
|---|---:|---:|---:|---:|
| Antalya 2023 | 620 | 490 | 130 | 480 |
| Antalya 2024 | 508 | 347 | 161 | 340 |
| Antalya 2025 | 212 | 50 | 162 | 49 |
| Dalaman 2023 | 8 | 0 | 8 | 0 |
| Dalaman 2024 | 18 | 0 | 18 | 0 |
| Dalaman 2025 | 53 | 0 | 53 | 0 |

Antalya's unresolved subset is **887/1,340** archived pixels (66.19%); its other subset is 453. NOAA-20 contributes 246/173/26 unresolved pixels across 2023/24/25; S-NPP contributes 244/174/24. All 869 source type-2 Antalya records fall inside these two bins in this fixed archive. The original 620→212 total change and 490→50 unresolved-subset change are **archive composition changes**, not wildfire incidence or trend estimates. The other subset changes 130→162; it is also not a validated fire population. Sensor acquisition, quality and source classifications can differ across years. The [FIRMS type guide](https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_VIIRS_Firehotspots.html) and [static-mask caveat](https://firms.modaps.eosdis.nasa.gov/descriptions/Static_Thermal_Anomalies_Mask.html) preclude treating type-0 as confirmed vegetation fire or type-2 as an independently established industrial site. **Independently established non-wildfire exclusions: 0.**

## Agency perimeter evidence: actual numerical result

The fixed Sacramento query yields **9 official final mapped perimeters**: three each in 2023, 2024 and 2025. Five records (FOOTHILLS, BREWER, CATLETT, SUNSET, MOORE) carry a wildfire suppression management objective and a source geometry method of GPS Ground (four) or GPS Air (one). They provide stronger geolocated evidence of a mapped fire perimeter than an archived hotspot. The other four use infrared, other imagery or photo interpretation and/or have a missing management objective. All nine have source calendar alarm dates; none has a verified ignition coordinate, verified event-discovery lineage, or a demonstrated first availability at the historical decision time.

The source's `C_METHOD` code documents **how the final perimeter was collected**. It does not alone establish how the incident was first discovered, that every record is independent of every satellite-derived product, or that the perimeter is a direct on-ground physical-event adjudication. FRAP explicitly warns that [its perimeter layer is incomplete](https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/California_Historic_Fire_Perimeters/FeatureServer/0), with minimum size/impact criteria, missing records and possible duplicates or over-generalization. Therefore **0 verified negative outcomes** and **0 verified negative cell-dates** are available from this source. An unlisted fire, place or day remains unknown. The 9-feature count is the query result, not the number of all fires in the box.

## Satellite acquisition and model decision

The NOAA-20 L1/L2 original granule-content requests still redirect to Earthdata Login and return HTTP 401 without an already authorized credential. The [Phase 3 standard-product audit](antalya-standard-viirs-model-readiness-2025-01.md) remains catalog context only. No cell-level swath, invalid/cloud mask or complete fire-mask array was inspected. The FRAP California records do not fill the Antalya satellite-exposure gap or form a compatible negative observation population. The [outcome cohort](../../public/data/sacramento-frap-outcome-cohort-2023-2025.json) and [sensitivity aggregate](../../public/data/turkey-static-sensitivity-2023-2025.json) consequently mark wildfire occurrence modeling **ineligible**. Models trained: **0**; forecasting skill, calibration and fire-rate differences: **not estimated**.

## Offline replay, tests and cost

```sh
python -m fire_public.frap_outcome_cohort \
  --geojson docs/research/source-samples/sacramento-frap-2023-2025.geojson \
  --metadata docs/research/source-samples/sacramento-frap-layer-metadata.json \
  --count docs/research/source-samples/sacramento-frap-count-2023-2025.json \
  --output /tmp/frap-replay.json
python -m fire_public.static_sensitivity \
  --manifest examples/antalya-annual-manifest-2023-2025.json \
  --regions-json examples/annual-spatial-regions-2023-2025.json \
  --spatial public/data/turkey-spatial-recurrence-2023-2025.json \
  --raw-dir /private/verified-turkey-annual-originals \
  --output /tmp/sensitivity-replay.json
```

The second command requires the six unmodified source CSVs named by the manifest in an **outside-Git** directory. Replay checks their exact SHA-256. The checked-in aggregates are 10,018 and 6,603 bytes, respectively. Local byte-identical replays took 0.053 s / 27,388 KiB child peak RSS (FRAP) and 3.553 s / 32,956 KiB child peak RSS (FIRMS; 257,907 source rows), one run each on Python 3.14. The two small FRAP original responses total about 80 KB and remain reviewable in Git; the large NASA archives remain outside Git. No Worker KV, paid resource or persistent process is added. CI uses pinned source samples and aggregate integrity; the full real FIRMS replay is a local verification because live external downloads do not gate PR CI.

**Next evidence step:** authorized original VIIRS granule contents for predefined cell-acquisitions, and record-level review of independent incident detection/verification plus coverage of non-event units. Only then define a prospective occurrence target, valid positives/negatives and a separated evaluation design.
