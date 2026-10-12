# NWS forecast change analysis slice

**Goal:** Make the selected US agency incident's weather panel answer how forecast conditions change over the next 6, 12, and 24 hours, without presenting those differences as fire spread or ignition predictions.

**Scope:** Compare the already fetched NWS grid values to the 0-hour row. Show signed changes in wind speed, gust, temperature, and relative humidity, plus the shortest angular wind-direction turn. Preserve unknown fields as unknown. Keep each rain amount tied to its original forecast interval; do not sum overlapping intervals. The source update, receipt time, grid link, stale state, and validity intervals remain visible. No new API calls, KV writes, or background jobs.

**Tasks:**

1. [x] Add pure-function tests for signed changes, direction wraparound, missing values, and invalid/duplicate row horizons.
2. [x] Implement the comparison in `public/weather-context.mjs` and a readable, translated summary in the incident weather panel.
3. [x] Extend local desktop/mobile browser acceptance to verify a real comparison row and the no-fire-prediction caveat.
4. [x] Run Python, JavaScript, and browser gates. Update the product documentation and draft PR with exact scope and limits.

**Acceptance:** A value absent at either endpoint produces an unknown change; 350° to 10° is a 20° turn rather than 340°; zero is distinct from missing; stale or missing forecasts cannot produce a fabricated comparison. Users can see that these are forecast condition changes at a grid point, not effects on the fire.
