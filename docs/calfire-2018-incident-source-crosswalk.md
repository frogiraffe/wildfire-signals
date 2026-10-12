# Live CAL FIRE 2018 incident-name corroboration (source leads only)

The existing 2018 Northern California research study queries NIFC historical fire perimeters and USGS/USFS MTBS burned-area occurrence points for the same area. This optional third official source adds **CAL FIRE’s public 2018 historical incident archive**, which publishes incident names, start dates, counties, final reported acreage and links to individual official incident pages.

Source: https://www.fire.ca.gov/incidents/2018

## Capture and cross-reference real source records

    python -m fire_public.calfire_incident_archive \
      --study-dir /private/wildfire/california-2018 \
      --output-dir /private/wildfire/calfire-2018-original

The CLI fetches the **single fixed official HTTPS URL** without following redirects, bounded to 6 MiB; it requires a structured five-column 2018 incident table and valid event-page links on the same official domain. No arbitrary URLs, user credentials or paid resources are involved.

It saves exact original HTML as `original-calfire-2018.html` and a derived `original-calfire-cross-reference.json` including the original content SHA-256, snapshot time, reported CAL FIRE event name/date/counties/acreage, source event page link, and per-candidate comparisons. The output directory must not already exist. An offline `replay(study_dir, archive_dir)` method reparses source bytes and compares the entire original-source-derived report.

Both original NIFC and MTBS study archives undergo the existing strict SHA-256, source-ID and geometry verification **before** CAL FIRE comparisons.

## Scope of the comparison

- Name comparisons are `exact_normalized_name_only` or `distinctive_token_shared_not_identity`, and retain **all** potential incident archive rows for ambiguously repeated names. They are *possible historical research leads*, not verified same events.
- The CAL FIRE archive contains a retrospectively reported starting date; where the MTBS record has a date, the tool records only exact calendar-day agreement/disagreement. The original NIFC dataset does not establish a comparable ignition date for this workflow.
- The CAL FIRE historical archive is not a geographically complete 2018 incident inventory; it contains source-reported event entries without sufficient geographic geometry to verify the exact Northern California study rectangle. County names provide context but are not an exact spatial filter.
- The archive may contain missing/invalid dates or dates from another year. These are preserved and flagged rather than silently corrected.
- **CAL FIRE shares upstream agency information and may overlap with NIFC/MTBS**. A third official website is not proof of statistically independent event identification.
- If a name does not appear in CAL FIRE, this does **not** establish a missing wildfire, nonfire, model false positive or any kind of detection accuracy result.
- No original-source link is automatically transferred into the private independent human evidence archive as a "verified independent source"; it must pass separate licensing, source-lineage and adjudication checks.

This pilot is pinned to CAL FIRE **2018 only** until the official page format, rights, archival stability and inclusion semantics have been verified for other years.

## Verification

Python tests use synthetic HTML tables and source-shaped original government fixtures to exercise name collisions, source dates, malicious external URLs, incomplete data, tampered raw HTML, altered cross-reference JSON and original NIFC/MTBS corruption.

The existing GitHub Actions real-region study also downloads CAL FIRE’s **actual 2018 official incident archive HTML**, stores byte-exact source evidence and compares it with the same genuine NIFC/MTBS regional sample. CI asserts that zero ground-truth event identities, nonfires or calibrated forecasts were produced.

**Scientific status:** three authentic historical source products, linked for researcher review. Zero independently verified fire event matches and zero independent true-negative samples.
