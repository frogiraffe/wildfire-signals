# Agency status time-series pilot

**Goal:** Analyze the local CWFIS historical status records as source-reported intervals, exposing transitions, reversals, gaps, and receipt-time limitations. Do not infer fire extinction or predict its future.

**Contract:** The query is read-only and as-of-gated. It uses only records received by the query time, handles later corrections at the same source start time, validates status and interval boundaries, and reports missing coverage instead of filling gaps. A later out-of-control status after under-control is a reversal, not proof of flare-up timing. Area values are not converted to growth rates without a documented unit and measurement contract.

**Tasks:** [x] Add focused tests; [x] implement CLI; [x] run on both local CWFIS pilots; [x] document measured transitions and why this is not an outcome label; [x] run full gates.
