# Wildfire Signals (pre-release)

This is the public, standalone collector and map. It contains no private repository
history or credentials. The [preview map](https://wildfire-signals.pages.dev/)
is live with hourly hosted collection. It is not a stable 1.0 release.

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
For a new account whose subscriptions API returns an empty first page, the gate
also requires an account-specific dashboard Free-plan attestation in
`CLOUDFLARE_FREE_ATTESTED_ACCOUNT_ID`. This value must match
`CLOUDFLARE_ACCOUNT_ID`; a paid subscription is always rejected.

At most one scheduled run per hour performs two KV writes. Each immutable snapshot
is gzip compressed, capped at 5 MiB and expires in seven days; the current pointer
is written last.
Uncached map requests make two KV reads, or three while an older version is used
during KV propagation. The 10,000 visits/day target implies 20,000–30,000
reads/day, below the current 100,000/day Free limit. This is a design
budget, pending load and real-data measurements. Public Actions standard runners
are free for public repositories.

The site requires a Pages project named `wildfire-signals`, with repository root
as project root, `public/` as build output, and a sibling `functions/` directory.
The checked-in `wrangler.toml` supplies the `PUBLIC_SNAPSHOTS` KV binding.
`/api/*` is the only Function route.
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
   only reads subscription information. If Cloudflare returns no subscriptions,
   first confirm Workers & Pages shows **Free** with no paid add-ons, then set
   `CLOUDFLARE_FREE_ATTESTED_ACCOUNT_ID` to the same Account ID. A paid, unknown
   or unverifiable response fails closed and creates no resource.
4. Connect this repository to Cloudflare Pages as project `wildfire-signals`,
   with repository root `/`, no build command and output directory `public`.
   The classic KV namespace has already been created and its binding is in
   `wrangler.toml`; confirm it appears in the deployed Pages project. Set the
   actual `https://<project>.pages.dev/api/snapshot` URL as a repository variable.
5. The Free check, initial snapshot size and live endpoint have been checked.
   `ENABLE_PUBLIC_COLLECTION=true` is enabled for hosted hourly collection;
   the developer's computer need not stay on. Each run repeats the Free gate.

The source-only pilot was disabled after the live hosted collector succeeded,
avoiding duplicate FIRMS requests. Observe the live preview for seven days from
10 October 2026, checking gaps, source freshness, Free quotas, browser behavior
and real traffic before a 1.0/stable release claim.

## Local checks

```sh
python -m unittest discover -s tests -v
node --test tests/js/*.test.mjs
```

Review missing and failed scheduled collection intervals using GitHub's workflow
run history. The earlier source pilot audit covers only its own fixed window and
does not make a release decision on its own:

```sh
gh run list --workflow source-pilot.yml --limit 200 \
  --json createdAt,status,conclusion,event,databaseId > pilot-runs.json
python -m fire_public.pilot_audit pilot-runs.json
```
