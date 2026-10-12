# Offline MTBS–NIFC Pair Review Workbench

The [same-year shared-region study](mtbs-nifc-shared-region-study.md) identified NIFC and USGS/USFS MTBS records from one historical WGS84 region and year, yielding **geographic search candidates**. This implementation turns the source-backed candidates into a **private, offline, interactive review packet**. It does not automatically infer that nearby records represent the same incident.

## Prepare genuine source data

Run the established region study against the actual, pinned government APIs:

```bash
python -m fire_public.mtbs_region_study \
  --year 2018 --bbox -123 38 -120 41 \
  --limit-per-source 30 --radius-km 20 \
  --output-dir /private/wildfire/region-2018
```

Then create an individual independent researcher's private packet:

```bash
python -m fire_public.mtbs_match_review packet \
  --study-dir /private/wildfire/region-2018 \
  --reviewer-id researcher-a \
  --html /private/wildfire/researcher-a-pairs.html
```

Open the resulting file directly in the browser (`file://`); **no server**, API key, web requests or account is required. The interface displays:
- original year and region,
- original source IDs, names, MTBS fire type (including possible prescribed burns), provider-reported acreage, retrospective MTBS source date, centroid coordinates and NIFC GlobalID,
- an offline SVG **relative-geometry preview** of the NIFC polygon and MTBS point (downsampled for display, *never* substituted into scientific geometry validation),
- a per-pair human review disposition: **possible same event**, **possibly distinct events**, or **inconclusive**,
- mandatory explanation and HTTPS external evidence URL for non-inconclusive hypotheses.

This is not an independent ignition-time review, validated fire-absence frame or adjudicated binary wildfire prediction label. Evidence links are user-provided; neither the browser nor the validator authenticates the cited external source. Each pair remains a hypothesis.

Researcher responses live in the current browser page until explicitly downloaded. There is **no autosave**. Do not close the page before exporting, and keep vote files and personal reviewers' material outside the public repository.

## Tamper-resistant source loading before generating the packet

`load_study` replays the *original government response bytes* against the existing `aligned-study.json`:

1. Verify all raw provider file SHA-256 hashes and exact byte lengths, including original NIFC/MTBS source-region ID lists and ArcGIS feature pages.
2. Recalculate published source-region ObjectID population counts and source-ID digests; rerun the exact per-provider seeded selection and check retrieved original selected ObjectIDs.
3. Reparse full source NIFC polygons and MTBS point attributes, checking geometry and original per-record feature digests before exposing names, reported acres, ignition-date fields and fire types.
4. Recompute every point-to-polygon search-radius spatial candidate from original geometry; reject omitted, added, duplicated or prematurely "verified" pairs.
5. Bind the reviewed JSON output to the SHA-256 of the **exact original study report bytes**, and require explicit dispositions for each candidate.

This protects against accidentally reading a stale/mismatched study, truncated source response, or a selectively edited candidate set. Byte hashes are **not digital signatures from the publishers** and do not prove that the government data include every wildfire.

## Validate the private exported review

```bash
python -m fire_public.mtbs_match_review validate \
  --study-dir /private/wildfire/region-2018 \
  --votes /private/wildfire/researcher-a-pair-review.json \
  --output /private/wildfire/researcher-a-audit.json
```

The resulting JSON reports counts in three explicitly **unverified hypothesis** categories. It always states `same_event_verified=0` and `negative_labels_created=0`. Missing or repeated pair votes, tampered source report bytes, invalid URLs, missing rationales or source SHA mismatches are rejected. An inconclusive case is an appropriate conclusion, not a failed label.

Votes are not imported into `label_review finalize`. That workflow has different, independent positive/nonfire adjudication and coverage requirements; **a pair hypothesis is never a training label or a ground-truth match**.

## Real CI evidence and tests

The original two-provider live-GitHub-Actions job now builds the HTML reviewer packet from its **actual 2018 Northern California NIFC/MTBS capture**. The downloaded artifact contains the original official source byte files and the portable HTML, but **no private human reviews**.

A dedicated regression workflow runs original-data integrity checks and desktop/mobile Chromium tests against a provider-shaped synthetic fixture, including local `file://` loading, the SVG preview, multi-case navigation, no network requests, evidence validation, actual JSON download and Python revalidation. Browser fixtures are not real wildfire-event conclusions.

**Research status:** experimental retrospective case-investigation tool. A confirmed same-incident relationship would require separate human/source identity corroboration and an explicit confidence protocol; independent binary wildfire outcomes, true nonfire cases, forecasting calibration and model skill remain unverified.
