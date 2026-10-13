# Private CAL FIRE–NIFC–MTBS source-lineage reconstruction

**Experimental and offline.** This follows [CAL FIRE alternative-page dossiers](calfire-alternative-event-dossiers.md) and [blind source-lead review](calfire-blind-alternative-review.md). It **does not** identify independently verified same-fire events. It reconstructs evidence paths so human researchers can determine which original archives, citations and retained document bytes must be investigated further.

## Input contract

The command **replays all original NIFC/MTBS, annual CAL FIRE and candidate-linked incident-detail source files**, rechecks source SHA-256 and batch completeness, then restricts the reviewer-focused analysis to original cases with multiple CAL FIRE candidate links. The original California 2018 research pilot includes 14 geographic candidates; 7 have more than one candidate-linked CAL FIRE source page.

Optional human review inputs: two **separately** completed, [casebook-SHA-bound](calfire-blind-alternative-review.md) reviewer vote JSON files. Optional private documentary evidence inputs: pre-existing [third-party source receipt store](mtbs-independent-event-evidence.md) produced by `python -m fire_public.mtbs_event_corroboration capture`. Receipt verification replays the existing manifest and original archived document SHA values; declared publisher identities and document authenticity remain unverified externally.

A reviewer evidence URL is joined to a documentary receipt by **exact HTTPS URL and the same original candidate identity**, not a fuzzy search or shared domain. The feature flags conflicting votes, a citation without exactly one archived document, document bytes reused across different cited URLs, claimed common upstream family, duplicate publisher/source record IDs, reviewer citation reused across cases, original CAL FIRE page used as its own third-party proof, source publication after the reviewer decision, and documents first preserved *after* the vote. Source timestamps are evidence metadata, not decision-time predictor features.

## Offline invocation

Original paths shown are examples only; replace them with real private local directories:

```sh
python -m fire_public.calfire_lineage_audit \
  --study-dir /private/wildfire/california-2018 \
  --calfire-archive-dir /private/wildfire/calfire-2018 \
  --batch /private/wildfire/calfire-detail-batch-0 \
  --batch /private/wildfire/calfire-detail-batch-6 \
  --batch /private/wildfire/calfire-detail-batch-12 \
  --first /private/wildfire/alice-filled-votes.json \
  --second /private/wildfire/bob-filled-votes.json \
  --private-receipts /private/wildfire/private-document-store \
  --output-dir /private/wildfire/lineage-audit-001
```

Leave out both `--first` and `--second` if no real reviewers have completed independent assessments, and omit `--private-receipts` when there are no genuinely captured documentary receipts. Synthetic test fixtures are **not** original independent documentation.

The output is a **new private folder** containing `private-lineage-audit.json` and `private-lineage-audit.html` (no JavaScript, no remote resources, restrictive content security policy). The machine-readable report contains a deterministic, source-identity-based directed graph: geographic candidate → NIFC / MTBS original record → candidate-linked CAL FIRE incident page, and candidate → exact captured private evidence receipt. Each relationship explicitly records that it does **not** prove independent physical wildfire identity. Do not publish raw outputs: reviewer identities and private source URLs may be present.

Readiness states are intentionally conservative:

- `awaiting_independent_human_reviews`: no completed paired human review.
- `unresolved_human_hypotheses`: reviewers disagree or abstain.
- `source_lineage_or_citation_gaps`: reviewers agree on a source lead but documentary and structural checks still flag issues.
- `structurally_reviewable_not_authenticated`: two distinct, timely and locally preserved documents claim consistent original provenance and two reviewer hypotheses agree; **still not an authenticated wildfire event**.

Original source SHA-256 is evidence of **byte preservation**, not upstream independence, genuine authorship or fire identity. Claimed publishers and families cannot become authenticated through this process. Missing CAL FIRE page matches never produce negatives. No outcome labels, predictive probability or model skill measurement are emitted.

## Validation

```sh
python -m unittest discover -s tests -p 'test_calfire_lineage_audit.py' -v
```

Regression cases include original-source tampering, citation-to-receipt joins, private byte mutation, duplicate document bytes, common upstream family, late archival, shared citations, conflicting reviewers, no reviewers, new-only output protection, and zero automatic fire/nonfire labels. Runs are bounded, use synthetic private documents in unit tests and do not make live government API requests. The current US-only historical pilot is **not** a geographic limitation of the global Wildfire Signals product.
