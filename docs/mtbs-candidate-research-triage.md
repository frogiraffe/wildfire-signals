# Source-backed MTBS–NIFC research work triage

The same-region live pilot supplied real government NIFC perimeter and USGS/USFS MTBS large-fire mapping records. The pair-review workbench provided individual hypotheses and separate two-reviewer reconciliation. This addition prioritizes **human investigation workload**, explicitly not match likelihood or fire-prediction quality.

## Source-only real study command

    python -m fire_public.mtbs_candidate_triage \
      --study-dir /private/wildfire/california-2018 \
      --json /private/wildfire/work-queue.json \
      --csv /private/wildfire/work-queue.csv \
      --html /private/wildfire/work-queue.html

All outputs must be new and **outside the original source archive**. No new external request, paid service or deployment is needed. The HTML is static, source text is escaped, CSP denies scripts and connections, and the CSV protects against spreadsheet formula execution in untrusted source names.

The loader verifies the original region-year study, source ROI ObjectID lists and counts, seeded selected IDs, original NIFC/MTBS feature geometry and records, and every proximity candidate against archived government API response bytes and their SHA-256 digests. Any mismatch causes the work report to fail rather than silently changing the research sample.

The report retains counts of government-published source ObjectIDs and how many were actually sampled. These are **not** the population of all historical wildfires.

## Optional private two-reviewer decisions

After separate researchers complete their real manual pair reviews, use:

    python -m fire_public.mtbs_candidate_triage \
      --study-dir /private/wildfire/california-2018 \
      --first /private/wildfire/researcher-a.json \
      --second /private/wildfire/researcher-b.json \
      --json /private/wildfire/review-work-queue.json \
      --csv /private/wildfire/review-work-queue.csv \
      --html /private/wildfire/review-work-queue.html

The existing strict two-reviewer reconciliation validates both votes, their exact original source digest, reviewer separation, chronology, case completeness, HTTPS evidence and reviewer explanations. A contradiction or partial abstention moves a case to the front of the *research work* queue. Even full reviewer agreement never authenticates the event or original source independence. Private reviewer input and output stay outside the public repository.

## Why this is not a match score

Priority categories, in descending **manual work urgency**:

- unresolved_review_conflict — reviewers disagreed, or one abstained while the other proposed a relation.
- source_identity_ambiguous — one MTBS or NIFC record participates in multiple geometric proximity pairs.
- source_quality_follow_up — MTBS fire type is not plain wildfire, the MTBS retrospective date is unavailable, or there are no comparable distinctive source-name tokens.
- routine_manual_review — other records still needing actual independent corroboration.

A descriptive Jaccard ratio compares sets of Unicode-normalized distinctive name tokens, excluding generic words such as fire and incident. It is **not** an event-identity confidence, likelihood, model output or prediction quality metric. Different events can have identical names; one event can have different official names.

NIFC fire year is not an established precise ignition date. MTBS date attributes are retrospective. The report explicitly flags the absence of independently comparable source event-time evidence and does not calculate fabricated time differences.

Prescribed fires, ambiguous IDs, low name overlap, missing source records and mismatched candidates are not verified nonfires. All outputs preserve zero independently established event matches, zero independent nonfire labels, and no forecast-accuracy score.

## Live and offline verification

The existing live government 2018 Northern California regional job also exports the three work-queue files with its original provider source artifacts. Unlike the optional private review flow, the public CI path **does not invent or publish researcher votes**. Regression tests cover original source-byte integrity, consistent source-ID counts, name normalization, ambiguous candidate mapping, reviewer disagreements, date/type uncertainty, HTML injection, spreadsheet-formula safety and guarded outputs.

**Current status:** source-backed experimental investigative workload triage, not independent incident adjudication or wildfire prediction validation.
