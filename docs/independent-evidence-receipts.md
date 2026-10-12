# Independent research evidence receipts — immutable offline source archive

The independent wildfire label review system previously accepted **a declared HTTPS evidence URL and human reviewer attestations**, but had no way to prove that the researcher actually preserved the source bytes being cited. This extension supplies an optional **strict offline snapshot gate** for research export. It does not discover true nonfire cases or authenticate remote data by itself.

## What a receipt establishes

Each private evidence receipt pins:

- Exact SHA-256 and original byte length of a researcher-supplied document/file (max 5 MiB);
- declared external HTTPS source and rights URL, provider record identity, source type and declared original publication time;
- the review `case_id` and role (`label`, `primary`, `secondary` or `coverage`);
- actual time the local tool captured the file, allowing later reviewers to distinguish contemporaneous preservation from documents imported after review;
- optional, explicitly attested coverage region and time interval, required for negative-case third reviewer source.

The content-addressed private archive has `blobs/<SHA256>.bin` and `receipts/<SHA256>.json`, with separate deterministic receipt hashes. A changed byte, removed blob, altered receipt, wrong case ID/URL/role, wrong original label source record, late capture, incorrect negative coverage region or incomplete coverage window causes strict review validation to fail.

**Important:** The tool does **not** contact the HTTPS server or cryptographically authenticate the source organization. Bytes, publication timestamps, rights and complete incident-registry claims are supplied by a human operator. A stored SHA-256 means *these bytes stayed unchanged after capture*, not that the document was genuine or that missing fire records prove no fires.

## Capture a private independent source record

Store original source files and the archive **outside the public GitHub repository**. The receipt CLI deliberately never fetches arbitrary user URLs (avoids local SSRF), requests no API keys, and never sends privately reviewed data to GitHub Actions.

Example `label-source.json` — illustrative **not actual evidence**:

```json
{
  "schema_version": 1,
  "case_id": "frame:independent-2018-study-unit-001",
  "role": "label",
  "source_url": "https://example.org/registry/specific-event-record",
  "rights_url": "https://example.org/registry/terms",
  "source_kind": "independently_inspected_outcome_registry",
  "source_record_id": "event-001",
  "source_published_at": "2026-10-11T13:00:00Z"
}
```

First save the actual source document to `/private/wildfire/sources/event-001.pdf`. Then:

```bash
mkdir -p /private/wildfire/evidence-store
python -m fire_public.evidence_receipts capture \
  --blob /private/wildfire/sources/event-001.pdf \
  --metadata /private/wildfire/label-source.json \
  --store /private/wildfire/evidence-store
```

Repeat for reviewer A and reviewer B (`role=primary` / `secondary`) using each person's exact independently cited `evidence_url`. Snapshot capture must not postdate that reviewer's signed decision. The main label receipt must have the same `source_record_id` and URL as the coordinator's reviewed label source.

For the third-party negative coverage record, set `role=coverage` and additionally declare:

```json
{
  "coverage_region_id": "region-1",
  "coverage_start_at": "2018-07-01T00:00:00Z",
  "coverage_end_at": "2018-07-02T00:00:00Z"
}
```

The supplied coverage region and interval must match or enclose the **same** reviewed region and the complete human-declared registry audit interval. This structural check does not make an unverified negative valid. FIRMS thermal detections and missing historical perimeter records are not accepted as independently established nonfire sources.

## Audit and strict finalization

```bash
python -m fire_public.evidence_receipts audit \
  --queue /private/wildfire/unadjudicated-queue.json \
  --reviews /private/wildfire/reviews.json \
  --store /private/wildfire/evidence-store \
  --output /private/wildfire/receipt-audit.json
```

The JSON tells you which adjudicated cases are missing archived source snapshots and why. All archived content hashes are rechecked; no live network calls occur.

After the other human and sampling protocol gates have passed, enforce snapshot coverage:

```bash
python -m fire_public.label_review finalize \
  --queue /private/wildfire/unadjudicated-queue.json \
  --reviews /private/wildfire/reviews.json \
  --protocol /private/wildfire/protocol.json \
  --evidence-store /private/wildfire/evidence-store \
  --cohort /private/wildfire/cohort.jsonl \
  --manifest /private/wildfire/cohort-manifest.json \
  --summary /private/wildfire/cohort-summary.json
```

The new `--evidence-store` argument is **optional for backward compatibility**, but strongly recommended for a research cohort intended for external review. When supplied, missing source receipts cause a hard failure. The resulting cohort manifest retains source receipt bindings, the content-addressed source archive digest, per-source capture/publication timestamps and explicit `source_authenticity_externally_verified_by_tool=false` in the summary. Original source bytes stay private. The existing split/embargo/Brier evaluation is unchanged.

## Verification

```bash
python -m unittest discover -s tests -p 'test_evidence_receipts.py' -v
```

CI uses **synthetic local source documents and reviewer decisions only**, tests timestamp and source binding failures, SHA corruption, full successful source-to-cohort export and compatibility with earlier review functionality. Success is software validation, **not independently verified positive/negative source availability, scientific measurement or externally authenticated fire-free regions**.

## Remaining real research blockers

A full valid scientific study still needs genuinely independent outcome records, a defensible geography/time sampling frame, reviewed complete registry scope for nonfire windows, licensing, reviewer auditability and appropriately weighted evaluation. A file receipt alone cannot establish any of these. Never use this receipt system to turn an NIFC historical perimeter **absence** into a negative wildfire case.
