# CAL FIRE 2018: original incident pages for archived NIFC–MTBS candidates

The existing bounded Northern California 2018 source study returns 14 NIFC–MTBS *geographic candidates*. The actual CAL FIRE 2018 archive has 310 historical incident records; 12 candidate pairs share some distinctive source-name tokens with that archive, but **none of those are verified same fires**. This pilot follows a limited, deterministic set of the original **individual incident detail URLs** already present in the source-verified CAL FIRE archive.

## Run (only real CAL FIRE incident links; no arbitrary URLs)

First perform the existing NIFC–MTBS shared-ROI and CAL FIRE annual archive commands. Then:

~~~bash
python -m fire_public.calfire_incident_details \
  --study-dir /private/wildfire/california-2018 \
  --calfire-archive-dir /private/wildfire/calfire-2018-original \
  --max-pages 4 \
  --seed calfire-incident-detail-v1 \
  --output-dir /private/wildfire/calfire-incident-original-pages
~~~

Selection:

- Replays both original NIFC/MTBS study and CAL FIRE full annual HTML against the exact bytes and candidate IDs. Never silently trusts a modified derived JSON.
- Enumerates unique official \`https://www.fire.ca.gov/incidents/2018/...\` incident detail links from candidate name leads; orders by SHA-256 of a fixed seed and the URL; selects at most **8** and by default 4, *without inventing reviewed events*. The count of all available linked URLs is preserved.
- Fetches only those already-archived official links over fixed HTTPS (never follows redirects), max 2 MiB per page, and writes exact original page bytes, sha256, length, historical archive-link and related candidate identities.
- Parses the actual detail page \`h1\`, **Date Started**, original reported start clock text with *unspecified timezone*, reported acreage, counties and optional **Location** coordinates. Location may not represent the original ignition point.
- Compares original CAL FIRE annual archive title/date with page title/date, and records drift rather than silently changing either. Any absent/malformed essential page causes a hard failure.
- Optionally records great-circle distance between the CAL FIRE displayed location and MTBS mapped centroid, and whether that point is at most 20 km from an original NIFC mapped perimeter. These are historical *geographic context*, **not proof of same event identity** or verified ignition.
- Copies only public original incident-page HTML into the research artifact, not private human reviews or private third-party documents.

Original server responses are saved in \`calfire-original-detail-01.html\` and similar files, alongside \`detail-study.json\`. The offline \`replay(study_dir, annual_archive_dir, detail_dir)\` routine recomputes every selected URL, checks each byte checksum and recalculates title/date/location/geometry information from original bytes; edited metadata or original HTML cannot silently pass.

GitHub Actions runs the full **authentic NIFC + authentic MTBS + authentic CAL FIRE annual archive + 4 original individual CAL FIRE incident pages** pipeline, and keeps the original bounded research evidence artifact for seven days. Unit tests use explicitly *synthetic* provider-style HTML separate from those real checks.

## What can and cannot be concluded

These incident detail pages contribute official **historical CAL FIRE description and location**, but the agency may have provided records reused in NIFC/MTBS. Several geographic candidates may reference the same CAL FIRE page. Multiple names, county overlap or a near point do **not** verify a physical fire identity, source independence or event timing at original forecast time.

An absent CAL FIRE page, missing coordinates, a different day or no name lead never creates a negative wildfire case. The report always sets \`event_identity_crosswalks_verified = 0\`, \`negative_fire_labels_created = 0\` and \`prediction_skill_measured = false\`. No model, training, live global collector or public map changes are made.

Public source examples illustrating the *fields available*, not proof of these particular candidate matches: [CAL FIRE Carr Fire](https://www.fire.ca.gov/incidents/2018/7/23/carr-fire) and [Ranch Fire (Mendocino Complex)](https://www.fire.ca.gov/incidents/2018/7/27/ranch-fire-mendocino-complex).
