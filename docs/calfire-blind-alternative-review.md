# Blind CAL FIRE alternative-source review (experimental, 2018)

This offline human-research step follows the [SHA-replayed alternative casebooks](calfire-alternative-event-dossiers.md). The original 2018 northern California pilot had **14** NIFC–MTBS proximity candidates and **18** candidate-linked genuine CAL FIRE pages; **seven** candidate cases have more than one CAL FIRE name-linked option. The module makes *no* probabilistic match or actual-event adjudication claim.

## Prepare independent packets

Use original, unmodified archived source directories, **not** a hand-edited derived JSON document. The CLI replays every original NIFC/MTBS/CAL FIRE byte via the previous complete-matrix gate. Packet creation and reconciliation never access the network.

```sh
python -m fire_public.calfire_blind_review packet \
  --study-dir /private/wildfire/california-2018 \
  --calfire-archive-dir /private/wildfire/calfire-2018 \
  --batch /private/wildfire/calfire-detail-batch-0 \
  --batch /private/wildfire/calfire-detail-batch-6 \
  --batch /private/wildfire/calfire-detail-batch-12 \
  --reviewer-id reviewer-one \
  --output-dir /private/wildfire/reviewer-one-packet
```

Run this command a second time for **reviewer-two** in a different *private* output folder. Each packet includes `independent-packet.html` and `private-vote-template.json`. Do not publish filled votes, raw evidence documents, reviewer identity, or derived reconciliation in a public repository or Cloudflare Pages. The outputs are created new-only with mode 0600 for files, 0700 for directories on POSIX; existing outputs cannot be overwritten.

For every ambiguous candidate, replace the draft fields in the vote template. Allowed decisions:

- `unresolved`: no selected CAL FIRE URL, no external citation and `source_lineage="unknown"`. Give a review reason of at least 12 characters and an offset-aware `reviewed_at`.
- `prefer_source_lead`: select **exactly one of the archived official CAL FIRE URLs** for this candidate, provide an HTTPS external evidence URL and reason, and record one of `unknown`, `shared_upstream` or `potentially_independent_not_verified` as source lineage. This is a *provisional lead preference*, not physical-event identity.

Every candidate must be addressed, even if both reviewers are uncertain. The pair's independent original review files are not merged or shown to each other before intake. External citation URLs are reviewer-supplied context: the tool **does not** authenticate their contents, independent provenance, licensing, or temporal availability.

## Reconcile original reviewer files

```sh
python -m fire_public.calfire_blind_review reconcile \
  --study-dir /private/wildfire/california-2018 \
  --calfire-archive-dir /private/wildfire/calfire-2018 \
  --batch /private/wildfire/calfire-detail-batch-0 \
  --batch /private/wildfire/calfire-detail-batch-6 \
  --batch /private/wildfire/calfire-detail-batch-12 \
  --first /private/wildfire/reviewer-one-votes.json \
  --second /private/wildfire/reviewer-two-votes.json \
  --output-dir /private/wildfire/private-reconciliation
```

This produces `research-reconciliation.json`, with SHA-256 binding to the exact replayed source casebook and the content of both vote files. It preserves each reviewer's complete opinion and one of four classifications:

| Review relation | Output | Interpreting it |
| --- | --- | --- |
| Both select same original CAL FIRE page | `concordant_unverified_lead` | Agreement on a hypothesis only |
| Both select different original CAL FIRE pages | `conflicting_source_leads` | Preserve conflict; no automatic choice |
| One unresolved | `partially_unresolved` | No agreed source lead |
| Both unresolved | `both_unresolved` | No supported lead choice |

A shared reviewer evidence URL is explicitly flagged. So are observed source-lineage overlap, repeated original CAL FIRE incident URLs and reuse of the same lead by multiple research candidates. Different URLs or distinct reviewer IDs do **not** prove genuinely independent upstream records.

**Scientific status:** exploratory human-review workflow over archived genuine historical research sources. Independent same-physical-wildfire crosswalks: **0**. Verified nonfire outcomes: **0**. Wildfire forecast skill measured: **no**. The output is not accepted by the label-evaluation finalization pipeline; it must not be substituted for independently authenticated event IDs, event-time availability or unbiased negative sampling. The pipeline has no automatic promotion to a fire/no-fire label.

## Testing

```sh
python -m unittest discover -s tests -p 'test_calfire_blind_review.py' -v
```

The synthetic tests exercise source replay, file tamper refusal, SHA mismatches, duplicate/missing votes, illegal URLs and fake confirmed labels, peer review conflict preservation, strict output semantics and private new-only file writes. They are not real independent human reviews.
