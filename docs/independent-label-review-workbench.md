# Independent label review workbench: real evidence → review → audited cohort

This tool closes an important operational gap between the real US NIFC historical perimeter research archive and the existing `fire_public.labeled_evaluation` baseline command. It explicitly **does not** manufacture fire labels from polygons or unknown regions and does not claim that reviewer-provided links are authenticated automatically.

## Stage 1 — Build an unlabeled queue from *two distinct sources*

The already downloaded NIFC perimeter SQLite supplies **retrospective positive-context leads only** (historical year, agency identity, original name). These are not ignition dates, true prospective features or fully adjudicated wildfire outcomes.

The separate independently documented **region-time sampling frame** supplies candidate control units, but **every one starts unlabeled**, and any fire discovered during review must be labeled positive or excluded rather than assumed no-fire.

Create a private `frame.json` with real source provenance and a predeclared geographic/time sampling protocol:

```json
{
  "schema_version": 1,
  "frame_name": "Independent region-time enumerated research frame",
  "sampling_protocol": "Describe precisely the population, spatial unit, time window, coverage and sampling design",
  "frame_provenance": "Describe the origin, completeness and version of the independently enumerated units",
  "source_url": "https://your-independent-registry.example.org/frame",
  "rights_url": "https://your-independent-registry.example.org/terms",
  "units": [
    {"sampling_unit_id": "frame-unit-001", "region_id": "region-1",
     "latitude": 37.0, "longitude": -120.0,
     "decision_at": "2017-07-05T00:00:00Z"}
  ]
}
```

`example.org` and illustrative entries above are **templates, not real coverage evidence**. The official NIFC source is US-only through 2019, but region IDs are generic for future jurisdictional expansion.

```bash
python -m fire_public.label_review prepare \
  --perimeter-db /private/wildfire/nifc-study.sqlite3 \
  --at 2026-10-13T18:00:00Z \
  --year 2017 --year 2018 \
  --frame /private/wildfire/independent-frame.json \
  --seed audit-2026-v1 --max-controls 60 \
  --output /private/wildfire/unadjudicated-queue.json
```

The CLI verifies underlying sampled source IDs and feature SHA-256 before use, selects bounded external frame cases with reproducible seeded per-region balancing, saves the immutable frame file digest, provider and year batch provenance, and creates a **single unadjudicated review queue**.

The sampled frame region distribution is a *selection policy within an already selected source frame*: balancing does **not** make the results representative of all regions or correct for incomplete source reporting. Frame records are never prefilled as zero. Official perimeter candidates carry no event day or fire outcome label and require independent date/scope adjudication. Maximum queue: 400 leads (up to 240 official and 200 frame candidates).

## Stage 2 — Explicit human review records

Create a private `reviews.json`:

```json
{
  "schema_version": 1,
  "queue_sha256": "64_hex_sha256_of_exact_unadjudicated_queue_json",
  "decisions": [
    {
      "case_id": "frame:frame-unit-001",
      "status": "adjudicated",
      "label": 0,
      "event_id": "independent-sampled-unit-001",
      "region_id": "region-1",
      "decision_at": "2017-07-05T00:00:00Z",
      "feature_cutoff_at": "2017-07-05T00:00:00Z",
      "label_available_at": "2017-08-01T00:00:00Z",
      "label_verified_at": "2026-10-12T18:00:00Z",
      "label_source": "independent-complete-incident-registry",
      "label_source_id": "source-record-for-research-unit-001",
      "label_evidence_url": "https://your-independent-registry.example.org/checked-unit/001",
      "primary": {
        "reviewer_id": "person-1",
        "reviewer_label": 0,
        "independent_evidence_checked": true,
        "agrees_with_label": true,
        "evidence_url": "https://your-independent-registry.example.org/review-1/001",
        "reviewed_at": "2026-10-12T16:00:00Z"
      },
      "secondary": {
        "reviewer_id": "person-2",
        "reviewer_label": 0,
        "independent_evidence_checked": true,
        "agrees_with_label": true,
        "evidence_url": "https://your-independent-registry.example.org/review-2/001",
        "reviewed_at": "2026-10-12T18:00:00Z"
      },
      "negative_coverage": {
        "registry_complete_for_unit_window": true,
        "start_at": "2017-07-04T00:00:00Z",
        "end_at": "2017-07-08T00:00:00Z",
        "completeness_evidence_url": "https://your-independent-registry.example.org/coverage-001",
        "coverage_reviewer_id": "person-3",
        "reviewed_at": "2026-10-12T18:00:00Z"
      }
    }
  ]
}
```

This is a **structural example**, not evidence that this example window was fire-free. The review must include one decision for every queue case. Explicit `status=unresolved` or `status=excluded` is supported, but each requires a meaningful `reason` and is counted; silent dropping is rejected.

Every adjudicated case requires two *different reviewers* who independently vote on the **same** label, cite external evidence, and have review times after source availability. For **negative labels only**, an additional third independent reviewer must explicitly confirm that the incident registry's geographic/time coverage spans the entire declared target prediction horizon, with a source URL and later audit timestamp. No retrospective perimeter can be relabeled zero.

A verified **positive** also requires `independently_verified_event_at` within the declared `decision_at...decision_at+horizon_hours` window; NIFC's `FIRE_YEAR_INT` alone is insufficient. Labels need a source availability time later than the prediction decision, and feature cutoff cannot exceed the decision time.

## Stage 3 — Human-attested protocol and guarded export

Create a separate private `protocol.json` with the existing [independent evaluation manifest](independent-label-evaluation.md) fields, including declared target/horizon, study geography, labeling rules, frame, original source/rights and reviewer provenance. In addition, explicitly provide:

```json
{
  "coverage_attested_by": "Independent human coverage audit team",
  "coverage_attested_at": "2026-10-13T18:00:00Z",
  "coverage_evidence_url": "https://your-independent-registry.example.org/coverage-audit",
  "negative_coverage_audited": true,
  "independent_label_provenance_verified": true
}
```

These fields are **human attestations**, not facts proved by the script. Both positive and independently audited negative classes must be represented or export is denied.

```bash
python -m fire_public.label_review finalize \
  --queue /private/wildfire/unadjudicated-queue.json \
  --reviews /private/wildfire/reviews.json \
  --protocol /private/wildfire/protocol.json \
  --cohort /private/wildfire/cohort.jsonl \
  --manifest /private/wildfire/audited-manifest.json \
  --summary /private/wildfire/review-summary.json
```

Output includes the exact immutable queue, decision and protocol SHA-256 digests, explicit unresolved/excluded counts, the original sampling frame digest and cohort row identities compatible with `fire_public.labeled_evaluation`. Existing source files and outputs are never overwritten.

Then run the existing baseline workflow:

```bash
python -m fire_public.labeled_evaluation \
  --cohort /private/wildfire/cohort.jsonl \
  --manifest /private/wildfire/audited-manifest.json \
  --test-start 2018-01-01T00:00:00Z \
  --embargo-hours 168 \
  --output /private/wildfire/evaluation.json
```

This evaluation is only as credible as the external frame and adjudication. The exporter validates internal structure/times/provenance declarations **but cannot independently authenticate URLs, source coverage or reviewers' identities**. Case-control samples with deliberately balanced class counts do not support unweighted population prevalence or globally calibrated probabilities without explicit sampling weights and design-based evaluation.

## Test and real-data boundary

```bash
python -m unittest discover -s tests -p 'test_label_review.py' -v
```

Offline CI exercises the *real SQLite importer and existing baseline logic* with provider-shaped **synthetic** responses and review attestations. The existing real NIFC 2017/2018 eight-polygon CI job additionally produces an **unadjudicated queue with eight genuine NIFC leads plus two explicitly synthetic frame units**. This is a real-source *integration proof*; its control frame is **not independent field evidence**, and the CI must not output approved positive/negative labels or real-world model skill.

Before genuinely training a model, create and manually substantiate a real, representative target-specific region/time frame and independent nonfire evidence. This code does not and cannot supply those on its own.
