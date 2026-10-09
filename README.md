# Fire Monitor Public Map (pre-release)

This is the public, standalone collector and map. It contains no private Fire Monitor
repository code, credentials, or production data. The service is **not deployed**.

## Data meaning

- NASA FIRMS VIIRS NOAA-20 and NOAA-21 pixels are grouped into 0.05-degree,
  one-hour **satellite candidates**. A candidate does not establish a fire.
- NIFC WFIGS `WF` and Canadian CWFIS active fire records are separate
  **agency incidents**.
- The current release does not associate a pixel cluster with an agency incident.
- Source failures produce `partial` status; a complete upstream outage keeps the
  previous published snapshot.

NASA FIRMS requires a free MAP_KEY. See <https://firms.modaps.eosdis.nasa.gov/api/area/>.
NIFC data comes from the [WFIGS current incident layer](https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations_Current/FeatureServer/0).
Canadian records come from the [CWFIS current active fire layer](https://cwfis.cfs.nrcan.gc.ca/downloads/docs/en/references/cwfif/cwfis-data-placemat.pdf)
and use the [Open Government Licence — Canada](https://cwfis.cfs.nrcan.gc.ca/downloads/licence.txt).
Attribution: Canadian Forest Service, Canadian Wildland Fire Information System
(CWFIS), Natural Resources Canada, Northern Forestry Centre, Edmonton, Alberta.
Map tiles use [OpenFreeMap Liberty](https://openfreemap.org/quick_start/).

## Zero-charge deployment gate

Deployment requires a verified Cloudflare Workers **Free** account and only Pages
static hosting, Pages Functions, and Workers KV Free. Do not enable Workers Paid,
R2, paid add-ons, or larger GitHub runners. The collector reads account subscriptions
before each KV write and rejects paid or unknown plans. KV Free quota exhaustion
causes a failed collection or stale map, not an automatic upgrade. Use a dedicated
API token with Billing Read and KV Storage Write, plus `FIRMS_MAP_KEY`.

At most one scheduled run per hour performs two KV writes. Each immutable snapshot
is capped at 20 MiB and expires in 25 hours; the current pointer is written last.
Uncached map requests make two KV reads. The 10,000 visits/day target implies
20,000 reads/day, below the current 100,000/day Free limit. This is a design
budget, pending load and real-data measurements. Public Actions standard runners
are free for public repositories.

The site requires a Pages project with root `public/`, `functions/` directory,
and a KV binding named `PUBLIC_SNAPSHOTS`. `/api/*` is the only Function route.
Set repository variables `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_KV_NAMESPACE_ID`,
and `PUBLIC_SNAPSHOT_URL`; set repository secrets `FIRMS_MAP_KEY` and
`CLOUDFLARE_API_TOKEN`. Keep the workflow disabled until the account, binding,
real-data size, source terms, and seven-day pilot have been checked.

## Local checks

```sh
python -m unittest discover -s tests -v
node --test public/*.test.mjs functions/api/*.test.mjs
```
