# MTBS–NIFC two-reviewer reconciliation (research hypotheses only)

The [source-verified MTBS–NIFC pair reviewer](mtbs-nifc-pair-review.md) exports independent research votes for every spatial candidate. This extension **compares two separate review files, flags conflicting opinions and correlated evidence citations, and provides a private read-only coordinator report**. It does not transform source proximity, event-name similarity or vote agreement into independent wildfire-event ground truth.

## Actual researcher workflow

First capture a bounded, genuine NIFC/MTBS same-region study, e.g. 2018 Northern California:

```bash
python -m fire_public.mtbs_region_study \
  --year 2018 --bbox -123 38 -120 41 \
  --limit-per-source 30 --radius-km 20 \
  --output-dir /private/wildfire/california-2018
```

Create **separate** portable reviewer HTML packets with different identities. Do not share their votes with each other:

```bash
python -m fire_public.mtbs_match_review packet \
  --study-dir /private/wildfire/california-2018 \
  --reviewer-id researcher-a \
  --html /private/wildfire/researcher-a.html

python -m fire_public.mtbs_match_review packet \
  --study-dir /private/wildfire/california-2018 \
  --reviewer-id researcher-b \
  --html /private/wildfire/researcher-b.html
```

Each person reviews the same original candidate set, sees the original mapped polygon/centroid and source names, records an **unverified working hypothesis** or explains why the relationship is inconclusive, and downloads a private JSON vote file.

After both people have finished, the coordinator compares independently submitted files:

```bash
python -m fire_public.mtbs_pair_reconcile \
  --study-dir /private/wildfire/california-2018 \
  --first /private/wildfire/researcher-a-votes.json \
  --second /private/wildfire/researcher-b-votes.json \
  --json /private/wildfire/private-comparison.json \
  --html /private/wildfire/private-comparison.html
```

The coordinator opens the **static HTML locally**, with no API, no browser JavaScript, and no network requests. The comparison presents both analysts' rationale and optional HTTPS evidence links alongside original MTBS ID/name/type/retrospective date and NIFC source identity. Do not upload these files to the public GitHub repo; they include private reviewer notes and identities.

## Explicit dispositions

- `concordant_unverified_hypothesis`: reviewers agree on *possible same* or *possible different* events. **Their agreement does NOT verify either claim.**
- `conflicting_hypotheses`: reviewer A suggests same event and B different, or vice versa. Needs human follow-up.
- `partially_inconclusive`: one reviewer abstained from drawing a relation.
- `both_inconclusive`: neither reviewer had enough evidence to choose a relation.

The report also flags reviewers citing the same URL (not two independent source confirmations), events participating in multiple geographic candidate pairs, MTBS source types not explicitly wildfire, and missing source event dates. Different URLs may still describe the same upstream agency records, so that remains uncertain.

## What is actually checked

The pipeline calls the existing `mtbs_match_review.validate_votes` for **each** review. This replays original government source bytes and requires matching source-archive SHA-256, every unique candidate ID, explicit decision/reason, HTTPS evidence for a non-inconclusive working hypothesis, original source IDs and geometry, and the unchanged proximity-candidate set.

It further requires distinct reviewer identities (case-insensitive), distinct vote files stored outside the source archive, and review timestamps not predating the original study capture. Output is new-only, with strict avoidance of source and private-vote overwrites. The JSON records the **exact SHA-256 of both vote files**, original source bundle, complete individual justifications, evidence links and unresolved statuses.

The HTML escapes untrusted source names, notes and reviewer identifiers and includes a restrictive Content Security Policy. The coordinator cannot turn its result into the binary fire/no-fire cohort via this command.

## Interpretation

Two people choosing `same_event_hypothesis` for a pair means **two people agreed on an unverified hypothesis**. It never counts as one successfully verified fire, a nonfire sample, ground-truth event identity or forecast-model accuracy. The actual case may involve prescribed burning, a retrospective MTBS centroid, multiple NIFC perimeter versions, or shared source incident records. Independent incident/date/source corroboration and appropriate adjudication are separate steps; this implementation records exactly what still needs to be checked.

CI uses **only synthetic review opinions**, not real human attestations, and validates agreement, disagreements, missing votes, mismatched source digests, same-identity submissions, impossible chronology, tampered provider bytes and HTML escaping. Real government regional source acquisition and portable packet generation are covered in the pre-existing NIFC/MTBS source workflow.

**Scientific maturity:** reproducible experimental review management. Confirmed event identities: **0**. Independent verified wildfire negatives: **0**. Validated model forecast skill: **not measured**.
