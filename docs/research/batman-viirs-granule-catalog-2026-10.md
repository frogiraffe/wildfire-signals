# Batman VIIRS granule catalog audit — 2026-10-09 to 2026-10-11 UTC

**Status:** exploratory source metadata comparison, 2026-10-14. No satellite observation opportunity, no-detection window, fire occurrence, or model performance is established.

## Question and sources

Can the short Batman FIRMS candidate archive be placed beside *independent satellite geolocation-product catalog metadata* without treating absent hotspots as negative observations? The 25 km Batman circle and dates are the pre-existing, outcome-selected station pilot. The FIRMS side is the same five verified project research scan receipts, ten SHA-256-pinned original pixel assets and local SQLite rollup used in [the station report](batman-station-thermal-context-2026-10.md). The catalog side is the NASA Common Metadata Repository (CMR), queried for the 375 m I-band geolocation products [VJ103IMG_NRT (NOAA-20)](https://www.earthdata.nasa.gov/data/catalog/lancemodis-vj103img-nrt-2) and [VJ203IMG_NRT (NOAA-21)](https://www.earthdata.nasa.gov/data/catalog/lancemodis-vj203img-nrt-2), collection version **2.1**. Those match the archived FIRMS platforms and nominal resolution. The previous roadmap suggestion of `VNP03MOD` was for the wrong platform and 750 m band.

The [CMR search API](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html) supplied public metadata. NASA's [data use and citation guidance](https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy) says unrestricted NASA-led mission data are CC0 by default, while restricted collection records must follow their marked terms; cite the named datasets and NASA. The exact two CMR JSON response bodies, request URLs, HTTP hit counts, per-response SHA-256 and fetch time are preserved in the [40 KB source snapshot](source-samples/batman-cmr-2026-10-09-11.json). No granule NetCDF file was downloaded or redistributed. The [14 KB public comparison](../../public/data/batman-cmr-context-2026-10-11.json) pins source hashes, original FIRMS scan receipt hashes, metadata revision times and its own content hash.

## Observation unit and method

- CMR query: `40.8,37.6,41.5,38.3` WGS84 bounding box, 2026-10-09 00:00 through 2026-10-12 00:00 UTC, separately for each product. The box includes the pilot circle, but a search hit only means a catalog spatial object intersects the query. We did **not** test actual 375 m geolocation pixels inside every pilot cell.
- FIRMS comparison unit: `provider × original UTC acquisition minute` among original pixels inside the existing Batman rollup. Count original pixels within each unit. This is not a count of independent fires or even distinct acquisition passes.
- A temporal catalog match requires the same platform product and `granule_start <= FIRMS minute < granule_end`. No timestamp tolerance is silently added. CMR granule metadata `updated` is a revision time, not proof of first publication. Original FIRMS first capture remains separately available in the report.
- The CMR snapshot is two complete, bounded query responses: both `CMR-Hits` headers equal the archived entry counts. Hashes and product IDs are validated before comparison. Empty or incomplete catalog results never become negative exposure evidence.

## Real results and interpretation

| Quantity | Observed result | Denominator / meaning |
|---|---:|---|
| CMR query results | 20 granules | 12 NOAA-20 plus 8 NOAA-21 metadata records intersecting the search box over three UTC dates |
| Archived FIRMS original pixels | 125 | Unique original pixels inside the existing 25 km study circle during the three UTC dates |
| Candidate provider-minute groups | 7 | Distinct provider × acquisition minute among those 125 pixels |
| Exact temporal matches | 5 | 5 of 7 provider-minute groups fall inside a same-platform CMR granule interval |
| Unmatched groups | 2 | NOAA-21 2026-10-10 10:11 and 2026-10-11 09:54 UTC; one precedes a catalog interval by a minute, the other sits at an interval's exclusive end |

The two unmatched times are a **source-time reconciliation finding**, not two failed overpasses. FIRMS acquisition-minute encoding, granule boundary conventions, or catalog/search differences require direct product inspection. The 20 catalog records do not form an observation denominator: bounding-box geometry is coarse, granule availability and cloud/quality data were not read, and a geolocation file alone cannot establish that the active-fire detection product was complete at any cell. Therefore the historical `satellite_observation_opportunity` field remains `unknown`, no zero candidate hours are introduced, and no fire occurrence regression or rate is calculated. The region was selected after looking at candidate counts; 5/7 is a metadata alignment fraction for this selected archive, not a global match rate or detection performance estimate.

## Reproduce

Fetch a new public metadata snapshot, outside the repository. A new fetch may differ as CMR records are revised. The committed snapshot permits exact offline replay without a network call:

```sh
python -m fire_public.acquisition_catalog fetch \
  --start-date 2026-10-09 --end-date 2026-10-11 \
  --bbox 40.8,37.6,41.5,38.3 --output /private/batman-cmr-new.json
python -m fire_public.acquisition_catalog report \
  --start-date 2026-10-09 --end-date 2026-10-11 \
  --bbox 40.8,37.6,41.5,38.3 \
  --snapshot docs/research/source-samples/batman-cmr-2026-10-09-11.json \
  --pixel-db /private/firms-pixels-with-batman-rollup.sqlite3 \
  --regions-json /private/batman-region.json \
  --output /private/batman-cmr-replay.json
```

`regions-json` must be the one-region array `[ {"region_id":"BATMAN_25KM","latitude":37.929,"longitude":41.1166,"radius_km":25} ]` with normal JSON whitespace. Create the SQLite rollup using `python -m fire_public.historical_rollup` and the two verified research releases described in [the analytics roadmap](../ANALYTICS_MODELING_ROADMAP.md). The report bytes are deterministic for the pinned snapshot, study contract and pixel archive. The public page shows the seven provider-minute comparison rows and links the compact report; it makes no operational forecast claim. CI uses the committed 40 KB snapshot and tiny synthetic SQLite fixtures, not live CMR requests or original pixel archives.

One local offline replay against the existing 240 MB real-pixel SQLite rollup produced identical report bytes in **0.06 s** wall time with **28,116 KiB** peak child RSS (Python 3.14, local machine); this is a bounded pilot measurement, not a full-history throughput claim. The source snapshot is 40,587 bytes and public report 13,795 bytes. No Cloudflare KV write, paid service, new secret or collector schedule change is involved.

## Next evidence gate

Download and hash one bounded original 375 m geolocation granule, inspect geolocation and quality fields against the actual candidate cells, then separately establish active-fire product completeness. Only after a region-time observation mask and product status are verified can a no-reported-detection state be considered. Independent wildfire outcomes require a separate label protocol. The CMR catalog adapter supports context now; it does not pass those gates.
