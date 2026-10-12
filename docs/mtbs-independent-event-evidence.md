# Independent event corroboration dossiers (private research)

The real NIFC–MTBS 2018 Northern California study yielded 14 geographically near candidates, not confirmed same-fire incidents. Two-reviewer agreements are still hypotheses. This tool creates a source-backed **empty evidence checklist** for each candidate and can privately archive original third-party incident records cited in human review decisions.

## Prepare genuine candidates without inventing evidence

    python -m fire_public.mtbs_event_corroboration prepare \
      --study-dir /private/wildfire/california-2018 \
      --output /private/wildfire/external-evidence-queue.json

This verifies the original NIFC/MTBS source bytes, selected record identities, original geometry, and complete candidate list. The output contains original MTBS/NIFC event IDs and names, MTBS retrospective date and an intentionally empty evidence checklist. The real 2018 CI job generates only this safe empty file, never fabricated third-party sources or human review opinions.

## Capture actual external incident documents offline

The operator, not the tool, must independently obtain a properly licensed source document, keep the bytes outside public GitHub, and prepare a bounded metadata JSON file. Example values below are placeholders and are **not actual independent California fire evidence**.

~~~json
{
  "schema_version": 1,
  "candidate_id": "2018:mtbs:100:nifc:1",
  "mtbs_fire_id": "REPLACE_WITH_GENUINE_MTBS_ID_FROM_CASEBOOK",
  "nifc_object_id": 1,
  "nifc_source_identity": "REPLACE_WITH_GENUINE_NIFC_ID",
  "source_url": "https://example.org/original-incident-report",
  "rights_url": "https://example.org/license",
  "publisher_id": "independent-event-provider-a",
  "upstream_family": "independent-event-records-a",
  "source_record_id": "ORIGINAL_EXTERNAL_INCIDENT_ID",
  "source_kind": "original incident report",
  "upstream_role": "firsthand_original_record",
  "relation_claim": "same_event_document_claim",
  "source_published_at": "2026-10-01T00:00:00Z",
  "source_event_at": "2018-07-20T00:00:00Z",
  "researcher_note": "Explain the claimed cross-reference between the two genuine source records."
}
~~~

Original source IDs must be copied from the real, prepared candidate casebook. Invented IDs cannot match the verified study. The document may be PDF, HTML export or another bounded original source snapshot.

    mkdir -p /private/wildfire/event-evidence
    python -m fire_public.mtbs_event_corroboration capture \
      --study-dir /private/wildfire/california-2018 \
      --store /private/wildfire/event-evidence \
      --metadata /private/wildfire/source-a.json \
      --document /private/wildfire/original-record.pdf

The capture step archives exact source bytes under a separate content-addressed private namespace with both document SHA-256 and canonical receipt SHA-256. Source publication and local capture timestamps are retained. The tool does not fetch arbitrary URLs, run paid infrastructure or upload any private source bytes.

A source from the original NIFC/MTBS URLs cannot be submitted as *third-party* evidence. Claimed publisher identity and declared upstream lineage are still supplied by the operator, **not authenticated** by the code. Different domains and upstream names do not demonstrate actual source independence.

## Compare with two real, distinct manual reviewer submissions

Researchers must independently complete the existing NIFC–MTBS offline pair-review packets and export separate private JSON results. For non-inconclusive decisions, each reviewer’s cited HTTPS source URL should have an archived original document, captured before their review.

    python -m fire_public.mtbs_event_corroboration audit \
      --study-dir /private/wildfire/california-2018 \
      --store /private/wildfire/event-evidence \
      --first /private/wildfire/researcher-a.json \
      --second /private/wildfire/researcher-b.json \
      --output /private/wildfire/source-corroboration-audit.json \
      --html /private/wildfire/source-corroboration-audit.html

The audit checks original NIFC/MTBS identities, integrity of each captured third-party document and receipt, source publication/capture chronology, agreement of source relationship claims with human citations, different declared upstream lineages, plausible event-time evidence, duplicate citations, missing supporting documents and contradictory review conclusions.

The optional local HTML report has no scripts or network access. It displays missing evidence gates and preserves the same scientific limitations. Identical source document bytes under multiple URLs are explicitly flagged rather than counted as independent supporting records.

A structurally complete dossier is only **ready for external independent adjudication**. It does not become a confirmed event. Outputs always report **0 verified event crosswalks and 0 verified nonfire labels**. A source’s absence from the archive is never evidence that a wildfire did not occur.

## Reproducibility, scientific boundary, privacy

- Actual source document bytes and votes remain private; CI publishes only original NIFC/MTBS records and an empty evidence queue.
- SHA-256 proves unchanged local bytes, not publisher authenticity, data truth or source independence.
- NIFC year is not independent ignition time; MTBS postfire centroids and dates are retrospective and include prescribed burns.
- Two reviewers agreeing on a hypothesis, or two documents with different claimed publishers, are not independently verified same-event relationships.
- This capability does not create model-training labels, observational negatives, forecast skill or live production fire coverage.

Research maturity: experimental external event-source dossier admission, pending **actual third-party incident records and authentic human adjudication**.
