# Same-region, same-year MTBS–NIFC official research capture

Earlier MTBS and NIFC pilots selected small source-ID samples from *different parts of the entire United States*. Their zero geographic overlaps were uninformative. The `mtbs_region_study` CLI improves research comparability by querying **the exact same geographic rectangle and the same historical fire year** on both actual government services *before selecting records*. This is still **not an independent event match or validated wildfire prediction dataset**.

## Small authentic Northern California 2018 pilot

```bash
python -m fire_public.mtbs_region_study \
  --year 2018 \
  --bbox -123 38 -120 41 \
  --limit-per-source 30 \
  --radius-km 20 \
  --seed wildfire-region-2018-v1 \
  --output-dir /private/wildfire/shared-region-2018
```

This uses:

- US NIFC *Interagency Fire Perimeter History* fixed HTTPS ArcGIS FeatureServer, filtered with `FIRE_YEAR_INT = 2018`.
- USDA Forest Service / USGS MTBS `2018 Fire Occurrence Locations` fixed HTTPS ArcGIS MapServer layer 70.

Both receive `geometryType=esriGeometryEnvelope`, `inSR=4326`, `spatialRel=esriSpatialRelIntersects`, and **the same** WGS84 `[-123,38,-120,41]` rectangle. For each, a source-ID list is fetched for the actual region; up to 30 records per source are deterministically selected by an explicit seed, and their original geometries and source attributes are read. The program pins the NIFC layer contract and the MTBS year-layer schema.

The resulting directory contains `aligned-study.json` and bounded **original source HTTP response bytes** for government ID lists, metadata and selected geometries, plus original SHA-256 and byte lengths. Result fields distinguish the *count of government records returned for the ROI* from how many were downloaded. Both source populations remain potentially incomplete inventories of wildfire events; even downloading all published ROI IDs does not establish national or complete wildfire coverage.

The optional `--radius-km` from 1 to 50 km defines a conservative MTBS mapped-point-to-NIFC-polygon **manual review proximity buffer**. Candidate output retains both original names, source IDs and MTBS `fire_type`. Proximity is **never** claimed to establish same event identity. MTBS mapped fire centroids are not guaranteed ignition locations and MTBS includes prescribed burns. A missing pair is not wildfire absence, a false negative, or a sensitivity estimate.

Research safeguards: single year (2017 or 2018), geographic extent no greater than 5×5 degrees, <=40 records per source, bounded source responses, no dateline-wrapping region, no user-specified HTTP endpoint, no paid service. Source objects outside the requested area, duplicate or incomplete feature pages, unrecognized source schemas and invalid coordinates fail closed; no data is published to the production map.

The first CI proof runs the same Northern California 2018 area on the two live official sources and retains a seven-day downloadable research artifact. Synthetic offline regression tests independently assert that both providers receive **identical** region/year query parameters, source-ID counts/selection digests are stable, raw source SHA checks pass, geometry responses actually belong to the requested ROI, and unsupported cases are rejected.

## Important methodological limits

Using the same geographic/time query is an **improvement in exposure and event investigation**, not proof of all local wildfires being observed. NIFC perimeter records and MTBS burned-area mapping have different inclusion rules, observation dates, fire-size thresholds, mapping availability and possible shared agency records. For meaningful pairwise conclusions, inspect original incident names, event dates, source identifiers, prescribed-burn flags, full polygon topology and the retrospective publication timeline; only then consider a human-adjudicated relation.

Relevant sources: [USFS MTBS ArcGIS service](https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MTBS_01/MapServer), [NIFC historical fire perimeters](https://data-nifc.opendata.arcgis.com/datasets/nifc::interagencyfireperimeterhistory-all-years-view/about).

Do not use paired or unmatched source points to generate independent negatives or to claim calibrated wildfire forecasting skill.
