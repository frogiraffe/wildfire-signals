# Batman VIIRS geolocation and active-fire product catalog comparison

Status: **experimental product metadata audit**, 2026-10-14 UTC. The first [geolocation catalog audit](batman-viirs-granule-catalog-2026-10.md) and real Batman FIRMS pixel archive define the region, 2026-10-09–11 UTC period, and seven archived provider-minute groups. This follow-up asks whether public NASA CMR also lists a corresponding NOAA-20/21 active-fire L2 product for each geolocation interval. It does **not** measure satellite observation opportunity, active-fire product completeness, no-detection, or wildfire incidence.

## Sources and population

| Source | Contract and evidence |
|---|---|
| NASA CMR public granule search | [Search API documentation](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html). Two bounded searches use `VJ114IMG_NRT` and `VJ214IMG_NRT`, version `2`, 2026-10-09T00:00Z through 2026-10-12T00:00Z and WGS84 box `40.8,37.6,41.5,38.3`. `CMR-Hits` must equal the returned entry count; the exact response bytes have SHA-256 hashes. A CMR spatial hit means a catalog geometry intersects the box, not every 0.05° candidate cell. |
| NOAA-20 active-fire L2 | [NASA VJ114IMG_NRT product page](https://www.earthdata.nasa.gov/data/catalog/lancemodis-vj114img-nrt-2). Twelve catalog granules; response SHA-256 `c41661ece29b702a8b2613c03c48d4ca4f2bba2c52e852c14efaee6499f28924`. |
| NOAA-21 active-fire L2 | [NASA VIIRS Collection 2 active-fire guide](https://www.earthdata.nasa.gov/s3fs-public/2024-07/VIIRS_C2_AF-375m_User_Guide_1.0.pdf) identifies the VJ214IMG family. Eight public CMR catalog granules; response SHA-256 `32f7ce5f9e7775d9e5f162fc93d3d2cd9b8019bc652d5a1ec3f70f322ca15ed1`. |
| Geolocation and archived candidates | The earlier source-hashed geolocation report has 20 L1 granules (12 NOAA-20, 8 NOAA-21) and 125 original FIRMS raw pixels grouped into seven provider × acquisition-minute units. Its evidence SHA-256 is pinned in the new report. |

The exact two-query [CMR source snapshot](source-samples/batman-active-cmr-2026-10-09-11.json) is 41,821 bytes (file SHA-256 `68b1000b105b64652107615cd563cdcceb38267caee27d25fea30607315ee3f8`). The [published paired report](../../public/data/batman-cmr-paired-products-2026-10-11.json) is 8,494 bytes (file SHA-256 `d04b9602fa4137cef326dea91f4a5fa74c6e140aea6169a4a28b2a39422c59d8`). NASA's [open data and citation guidance](https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy) applies; the report retains product names, collection versions, CMR query URLs, response hashes and metadata revision timestamps. Those revision timestamps are **not** proven first-availability times.

## Method and numerical result

The catalog unit is `platform × exact granule start × exact granule end`. Geolocation and active-fire records pair only when all three fields match. Candidate pixels remain grouped by original FIRMS provider and acquisition UTC minute; a group matches a product when its minute falls in that product's half-open `[start,end)` interval. No time tolerance is added and no spatial pixel or cloud mask is inferred from the CMR polygon.

| Measure | Result | Denominator |
|---|---:|---|
| Geolocation catalog entries | 20 | 12 NOAA-20 + 8 NOAA-21 box-intersecting L1 entries |
| Active-fire catalog entries | 20 | 12 NOAA-20 + 8 NOAA-21 box-intersecting L2 entries |
| Exact L1/L2 interval pairs | 20 | 20 distinct platform/time intervals in this bounded search |
| Archived provider-minute groups inside both catalog intervals | 5 | 7 groups among 125 archived raw pixels |
| Archived groups without either exact interval match | 2 | The same two NOAA-21 boundary-minute discrepancies in the earlier audit |

This improves the product availability **catalog** account: the bounded query lists a companion active-fire L2 record for every L1 interval. It does not show whether an L2 file contains complete data for the pilot cells, whether any cell was seen, or whether no detection was reported. The two unmatched FIRMS minutes remain source-time reconciliation questions. They are not failed passes. The pilot was selected after inspecting candidate observations and is not a global catalog reliability estimate.

## Reproduce

Fetch a fresh CMR snapshot only when source access is available; CMR metadata can be revised. The pinned snapshot permits deterministic offline replay:

```bash
python -m fire_public.acquisition_catalog fetch-active \
  --start-date 2026-10-09 --end-date 2026-10-11 \
  --bbox 40.8,37.6,41.5,38.3 --output /tmp/batman-active-cmr.json
python -m fire_public.acquisition_catalog pair-report \
  --geolocation-report public/data/batman-cmr-context-2026-10-11.json \
  --active-snapshot docs/research/source-samples/batman-active-cmr-2026-10-09-11.json \
  --output /tmp/batman-cmr-paired-replay.json
cmp /tmp/batman-cmr-paired-replay.json public/data/batman-cmr-paired-products-2026-10-11.json
python -m unittest discover -s tests -p test_acquisition_catalog.py -q
```

The web analytics page presents the L1/L2 catalog status per archived provider-minute group. A missing L2 report leaves the original L1 comparison usable. Original NetCDF files were not downloaded: a bounded anonymous LANCE GET redirected to Earthdata login, consistent with [NASA LANCE download access guidance](https://nrt3.modaps.eosdis.nasa.gov/help/). With authorized source access, the next evidence task is a predeclared cell/time quality and L2-content inspection; only then can an observation denominator be considered. Independent wildfire outcomes remain a separate requirement.
