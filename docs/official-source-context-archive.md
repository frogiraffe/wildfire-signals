# Immutable official NIFC source context beside independent reviewer evidence

This connects the existing **real official NIFC lead refresh** to a private
**content-addressed, offline-replayable research archive** and optionally to
the independent reviewer's local HTML form. It is a *non-label* source evidence
system. A government historical fire perimeter never becomes a confirmed
ignition-date event, independently validated ground truth, or a fire-negative.

## Capture direct official API responses into separate immutable context

Use the existing original historical perimeter SQLite and review queue:

```bash
mkdir -p /private/wildfire/official-evidence-store
python -m fire_public.official_lead_refresh \
  --queue /private/wildfire/unadjudicated-queue.json \
  --perimeter-db /private/wildfire/nifc-study.sqlite3 \
  --max-leads 8 \
  --context-store /private/wildfire/official-evidence-store \
  --json /private/wildfire/lead-refresh.json \
  --source-dir /private/wildfire/raw-http
```

This directly re-queries the **fixed official US NIFC FeatureServer HTTPS
endpoint**, verifies the provider's current ArcGIS schema, validates exact
selected ObjectIDs, year, GlobalID, WGS84 polygon geometry and source feature
SHA-256 against the original historical archive. It refuses a missing source
record or an unexpected identity change, but distinguishes legitimate source
revisions from original capture.

Original HTTP response bytes are now stored under the *separate namespace*:

- `official-context/blobs/<sha256>.geojson` — exact government response bytes
- `official-context/runs/<sha256>.json` — canonical immutable manifest tying
  those bytes and their source IDs to the original review queue SHA, source
  refresh report, year and capture time

This is deliberately **not** `receipts/`, which is the existing namespace
for *separately collected, independently adjudicated binary outcome* evidence.
No explicit or implicit conversion into review label evidence occurs.

The code accepts existing byte-identical manifests idempotently and rejects
altered blobs/metadata on later offline audits. The new context files are
read-only from the audit CLI perspective; keep them outside the public repo.
Operators should back them up, since the GitHub CI artifact is short-lived.

## Replay all government bytes without network access

```bash
python -m fire_public.official_context_archive \
  --queue /private/wildfire/unadjudicated-queue.json \
  --store /private/wildfire/official-evidence-store \
  --output /private/wildfire/official-context-audit.json
```

The audit revalidates original queue SHA, manifest integrity, raw HTTP byte
hashes, source year, ObjectID, GlobalID, polygon structure, feature hashes
and source-revision classification. Missing or altered files cause a hard
failure instead of being reported as "no fire". The optional
`--run-sha256` selects a specific immutable capture run when multiple
historical source refreshes are available; otherwise the most recent
capture time is selected.

The audit distinguishes `direct_pinned_official_https` from
`injected_test_transport`. **Saved bytes alone cannot prove which TLS
connection occurred**, so the transport is explicitly a run-time source
assertion, not a publisher signature or externally authenticated record.

## Review form can display authenticated-source *context*

```bash
python -m fire_public.review_form \
  --queue /private/wildfire/unadjudicated-queue.json \
  --official-context-store /private/wildfire/official-evidence-store \
  --reviewer-id researcher-a \
  --html /private/wildfire/reviewer-a.html
```

Each official perimeter case displays the observed source record status,
latest source capture timestamp and feature digest. **Frame-based
independent controls receive no NIFC context badge or spurious match.**
All cases remain initially unreviewed, and the historical NIFC lead still
cannot be voted fire-negative. Independent outcome links, agreement and
negative registry window coverage remain separate requirements.

Forms remain self-contained, network-free, CSP-restricted HTML that export
private JSON votes; no new background requests, client storage, paid
services or Cloudflare deployment were introduced.

## Real-source CI test

The NIFC multi-year GitHub Actions workflow already retrieves eight official
records in 2017 and 2018. It now additionally archives raw response bytes
into the context namespace, runs an independent offline audit, renders the
reviewer form from that archive and checks that **zero independent binary
outcomes and zero nonfire labels were created**. The published workflow
artifact includes only real *public* NIFC records and clearly synthetic frame
units; it does not contain any human reviewers' personal records.

Unit tests use injected synthetic source payloads and explicitly mark those
as `injected_test_transport`. Only the separate live CI workflow actually
checks the official HTTPS endpoint.

**Scientific maturity:** real provider source-provenance verification and
replay, but not independent fire occurrence validation. For actual prediction
metrics, we still need a scientifically defensible independent event registry,
verified spatial/temporal nonfire coverage, reviewer adjudication and suitable
holdouts.
