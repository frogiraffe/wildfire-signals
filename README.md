# Wildfire Signals (pre-release)

This is the public, standalone collector and map. It contains no private repository
history, credentials, or production data. The service is **not deployed**.

## Data meaning

- NASA FIRMS VIIRS NOAA-20 and NOAA-21 pixels are grouped into 0.05-degree,
  one-hour **satellite candidates**. A candidate does not establish a fire.
- NIFC WFIGS `WF` and Canadian CWFIS `OC`/`BH`/`UC` active fire records are separate
  **agency incidents**.
- The time window filters satellite observations. Agency records come from the
  current source layer; their source update date can be older than collection.
- Nearby satellite candidates and agency incidents may be linked **provisionally**
  by point distance. This does not confirm a fire or establish common identity.
- Source failures produce `partial` status; a complete upstream outage keeps the
  previous published snapshot.

NASA FIRMS requires a free MAP_KEY. See <https://firms.modaps.eosdis.nasa.gov/api/area/>.
NIFC data comes from the [WFIGS current incident layer](https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations_Current/FeatureServer/0).
Canadian records come from the [CWFIS current active fire layer](https://cwfis.cfs.nrcan.gc.ca/downloads/docs/en/references/cwfif/cwfis-data-placemat.pdf)
and use the [Open Government Licence — Canada](https://cwfis.cfs.nrcan.gc.ca/downloads/licence.txt).
Attribution: Canadian Forest Service, Canadian Wildland Fire Information System
(CWFIS), Natural Resources Canada, Northern Forestry Centre, Edmonton, Alberta.
Map tiles use [OpenFreeMap Liberty](https://openfreemap.org/quick_start/).
The [Europe plus Türkiye source inventory](docs/europe-official-source-inventory.csv)
currently lists all 52 M49 areas in scope. Its official feeds remain under review;
satellite candidates are the only current European coverage. This blocks a stable
release claim.

## Zero-charge deployment gate

Deployment requires a verified Cloudflare Workers **Free** account and only Pages
static hosting, Pages Functions, and Workers KV Free. Do not enable Workers Paid,
R2, paid add-ons, or larger GitHub runners. The collector reads account subscriptions
before each KV write and rejects paid or unknown plans. KV Free quota exhaustion
causes a failed collection or stale map, not an automatic upgrade. Use a dedicated
API token with Billing Read and KV Storage Write, plus `FIRMS_MAP_KEY`.

At most one scheduled run per hour performs two KV writes. Each immutable snapshot
is gzip compressed, capped at 5 MiB and expires in seven days; the current pointer
is written last.
Uncached map requests make two KV reads, or three while an older version is used
during KV propagation. The 10,000 visits/day target implies 20,000–30,000
reads/day, below the current 100,000/day Free limit. This is a design
budget, pending load and real-data measurements. Public Actions standard runners
are free for public repositories.

The site requires a Pages project with repository root as project root,
`public/` as build output, a sibling `functions/` directory,
and a KV binding named `PUBLIC_SNAPSHOTS`. `/api/*` is the only Function route.
Set repository variables `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_KV_NAMESPACE_ID`,
and `PUBLIC_SNAPSHOT_URL`; set repository secrets `FIRMS_MAP_KEY` and
`CLOUDFLARE_API_TOKEN`.

To connect the account without pasting a token into chat:

1. In the [Cloudflare dashboard](https://dash.cloudflare.com/), confirm the
   account uses Workers Free. Keep the free `pages.dev` address and decline paid
   products or upgrades.
2. Create a narrowly scoped [API token](https://dash.cloudflare.com/profile/api-tokens)
   for that account with **Billing Read** and **Workers KV Storage Edit**. Store it
   as the repository's `CLOUDFLARE_API_TOKEN` Actions **secret**. Copy the
   [Account ID](https://developers.cloudflare.com/fundamentals/account/find-account-and-zone-ids/)
   (32 hexadecimal characters) into the `CLOUDFLARE_ACCOUNT_ID` Actions
   **variable**. An API token is never an Actions variable. If one was placed
   there, delete it and revoke it in Cloudflare before creating a replacement.
3. Run the manual `Verify Cloudflare Free account` GitHub Actions workflow. It
   only reads subscription information. A paid, unknown or unverifiable response
   fails closed and creates no resource.
4. Connect this repository to Cloudflare Pages with repository root `/`, no build
   command and output directory `public`. Create a KV namespace and bind it to
   Pages production Functions as `PUBLIC_SNAPSHOTS`. Set the namespace ID and
   actual `https://<project>.pages.dev/api/snapshot` URL as repository variables.
5. Check the initial public snapshot size and the live endpoint before enabling
   `ENABLE_PUBLIC_COLLECTION=true`. That switch starts hosted collection; it
   does not use the developer's computer. Keep it unset until the Free check and
   binding are verified.

The seven-day source-only pilot runs on GitHub-hosted runners. It does not need
the developer's computer to stay on and does not publish to Cloudflare. After
the map implementation, source terms, Free account and initial size checks pass,
deploy a **preview** site and enable its hosted collector. Observe the preview
for seven days while it is live. Check gaps, source freshness, Free quotas,
browser behavior and real traffic before a 1.0/stable release claim. The source
pilot can continue independently; it is not a prerequisite to preview deployment.

## Local checks

```sh
python -m unittest discover -s tests -v
node --test public/*.test.mjs functions/api/*.test.mjs
```

After the fixed source pilot end plus two hours of scheduling grace, count missing
and failed scheduled intervals using GitHub's workflow run history. A run delayed
beyond two hours counts as a gap in its expected hour. This read-only audit does
not make a release decision on its own:

```sh
gh run list --workflow source-pilot.yml --limit 200 \
  --json createdAt,status,conclusion,event,databaseId > pilot-runs.json
python -m fire_public.pilot_audit pilot-runs.json
```
