# Decision-time evidence audit

**Goal:** Test whether the local agency and NWS archives can supply an honest historical model input at a specified decision time. Do not produce training labels or a prediction.

**Contract:** The caller explicitly identifies one agency incident and one NWS grid snapshot. The audit reads the two existing SQLite archives without mutating them. Agency and weather records must have been captured by the decision time. A weather snapshot must also be spatially close to a previously captured agency incident point; a shared or nearby coordinate is context only, never an identity merge. Missing location or late capture is a recorded exclusion, not a negative example. Output includes source IDs, capture times, distance, and exclusion reasons. Retrospective outcomes and later perimeters never enter the input set.

**Tasks:**

1. [x] Test unavailable-at-decision agency records, late NWS receipt, spatial mismatch, forecast validity, and a valid explicit match using synthetic SQLite fixtures.
2. [x] Add a small read-only CLI that emits the audit as JSON for one event and decision time.
3. [x] Run it against the local US/Canada pilot archives. Document exactly how many decision-time inputs exist and why this sample is or is not fit for model training.
4. [x] Run all tests and publish only source and audit findings in the draft PR. Keep raw source files and SQLite out of Git and Workers KV.
