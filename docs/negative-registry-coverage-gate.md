# Negative review cases: independent registry geography and observation-window gate

Previous independent label review required two human votes, a third negative-coverage reviewer, and optional SHA-256 archived source receipts. It did **not** validate that an external registry's declared **geography covered the whole sampled unit**, or that its **time-specific observation status** stayed continuously available for the full prediction horizon. This research-only extension adds those *structural* requirements, without pretending to authenticate provider data or to prove a real fire-free area.

## Study-frame footprint

The external independent frame used by `label_review prepare` can now include a **complete, closed geographic study footprint** per region-time unit:

```json
{
  "sampling_unit_id":"unit-2018-001",
  "region_id":"region-a",
  "latitude":37.02,
  "longitude":-120.00,
  "decision_at":"2018-07-05T00:00:00Z",
  "study_bbox":[-120.10,36.92,-119.90,37.12]
}
```

All four coordinates use WGS84 `[west,south,east,north]`. The sampled point must lie **inside the full study footprint**. If omitted, the regular private review queue still works, but the optional *strict coverage gate* will reject every such negative case, since the geographic extent of the proposed no-fire target is unknowable from a point and region name alone. Non-wrapping rectangles are supported; a study crossing the international date line must be explicitly split into separate non-wrapping units. No silent bounding-box interpolation.

## Declared independent-provider scope

Create a private `coverage-registry.json` describing the provider's declared spatial area, observation intervals and known outages. The example below is an **illustrative declaration**, *not evidence that any wildfire registry is complete*:

```json
{
  "schema_version":1,
  "areas":[{
    "region_id":"region-a",
    "provider_id":"independent-incident-registry",
    "source_url":"https://example.org/verified-coverage/region-a",
    "rights_url":"https://example.org/license",
    "source_record_id":"coverage-scope-region-a",
    "inclusion_protocol":"Document which incident types are reportable, spatial inclusion rules and data gaps",
    "coverage_bbox":[-121.0,36.0,-119.0,38.0],
    "windows":[
      {"start_at":"2018-07-05T00:00:00Z",
       "end_at":"2018-07-05T12:00:00Z",
       "status":"declared_complete"},
      {"start_at":"2018-07-05T12:00:00Z",
       "end_at":"2018-07-06T00:00:00Z",
       "status":"declared_complete"}
    ]
  }]
}
```

This exact source URL, original `source_record_id`, region and covered interval must be supported by an existing **private, SHA-256-verified coverage-role source receipt** created using `fire_public.evidence_receipts capture` and linked to the third independent coverage reviewer. The receipt must have been captured before the corresponding review decision. The operator-supplied registry itself is SHA-256 pinned to the resulting cohort manifest, but **its actual truth, license, geographic validity and incidence ascertainment still require independent examination outside the tool**.

If any `reported_gap` or `unknown` observation window overlaps the prediction horizon, the case fails, even if nominal `declared_complete` windows also cover that time. Separate complete windows may meet with no gap; one-minute holes fail. A point falling inside a provider's area is insufficient when any part of the declared study footprint is outside the provider's geographic bounds. Outages and uncertain periods never count as independently verified no-fire intervals.

## Audit before cohort export

```bash
python -m fire_public.negative_coverage_gate \
  --queue /private/wildfire/unadjudicated-queue.json \
  --reviews /private/wildfire/reviews.json \
  --protocol /private/wildfire/protocol.json \
  --registry /private/wildfire/coverage-registry.json \
  --evidence-store /private/wildfire/evidence-store \
  --output /private/wildfire/negative-coverage-audit.json
```

The audit reports each adjudicated negative decision as either `declared_scope_structurally_complete` or `not_admitted` with concrete reasons; no silent exclusion or negative-label fabrication.

For **strict** export, add `--coverage-registry` alongside the preexisting `--evidence-store` to the finalization command:

```bash
python -m fire_public.label_review finalize \
  --queue /private/wildfire/unadjudicated-queue.json \
  --reviews /private/wildfire/reviews.json \
  --protocol /private/wildfire/protocol.json \
  --evidence-store /private/wildfire/evidence-store \
  --coverage-registry /private/wildfire/coverage-registry.json \
  --cohort /private/wildfire/cohort.jsonl \
  --manifest /private/wildfire/cohort-manifest.json \
  --summary /private/wildfire/cohort-summary.json
```

If even one negative case fails geographic scope, time continuity, outage, source ID, or receipt binding, the cohort is **not** exported. Legacy research evaluation remains compatible when this new optional argument is not supplied. The manifest records the coverage-registry SHA-256, and explicitly sets `negative_registry_independent_completeness_verified=false`.

## Interpretation and remaining limitations

- Geographic *rectangle containment* is conservative and testable. It does **not** prove the provider actually operated throughout that rectangle; that is an explicit source claim.
- `declared_complete` means **operator-reported continuous observation**, not a verified complete fire census. It does not prove zero ignitions, all fire types captured, valid sampling weights, correct reviewer identities or actual incident reporting completeness.
- An existing label source receipt is checked by **exact bytes and claimed metadata**, not independently authenticated publisher signatures.
- Outside the tool, a defensible independent outcome registry needs documented mandatory reporting, publication lags, censoring and actual area/time coverage. Until then, zero scientifically validated negative wildfire examples exist.
- There are no new paid resources, background scheduled requests or live fire map changes.

## Verification

```bash
python -m unittest discover -s tests -p 'test_negative_coverage_gate.py' -v
```

Unit tests use synthetic provider documents and both positive and negative **fixture** decisions to demonstrate real binary-cohort structural export, full-frame spatial checks, adjacent-window merging, outage/unknown vetoes, incorrect source identity, tampered receipt bytes, missing study footprints and date-line refusal. Their pass/fail results are engineering verification, **not empirical wildfire forecast accuracy**.
