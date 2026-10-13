# Complete CAL FIRE candidate-linked incident-page matrix (2018 pilot)

The genuine Northern California 2018 shared-region study produced 14 NIFC–MTBS proximity cases and the CAL FIRE annual archive published 310 incident entries. The archive comparison identified 18 distinct name-linked incident detail URLs, of which the previous live pilot fetched four. This project now permits capturing the *entire candidate-linked URL population* via bounded source requests and creates a human-review research matrix.

## Real original-source capture

First run the existing NIFC/MTBS 2018 shared-ROI and CAL FIRE annual archive commands. Both store original provider responses and SHA-256 evidence.

Fetch the 18 known links in three batches with max 6 pages each:

    for offset in 0 6 12; do
      python -m fire_public.calfire_incident_details \
        --study-dir /private/wildfire/california-2018 \
        --calfire-archive-dir /private/wildfire/calfire-2018 \
        --max-pages 6 --offset "$offset" \
        --seed calfire-incident-detail-v1 \
        --output-dir "/private/wildfire/calfire-detail-batch-$offset"
    done

All detail requests use URLs already present in the genuine original CAL FIRE annual archive, restricted to the official 2018 HTTPS host/path. Stable SHA-256(seed, URL) ordering and explicit offsets permit deterministic continuation, while an absolute limit of 8 incident URLs per invocation bounds government service load. No credentials, paid infrastructure or background scraper are enabled. Any changed original-source URL population must be investigated and corresponding batch partition adjusted; gaps never imply fire absence.

## Source-verified investigation matrix

    python -m fire_public.calfire_incident_matrix \
      --study-dir /private/wildfire/california-2018 \
      --calfire-archive-dir /private/wildfire/calfire-2018 \
      --batch /private/wildfire/calfire-detail-batch-0 \
      --batch /private/wildfire/calfire-detail-batch-6 \
      --batch /private/wildfire/calfire-detail-batch-12 \
      --json /private/wildfire/complete-matrix.json \
      --csv /private/wildfire/complete-matrix.csv \
      --html /private/wildfire/complete-matrix.html

This **replays every original government source byte**: the regional NIFC/MTBS source study, annual CAL FIRE source HTML, and each bounded original CAL FIRE incident-page batch. It verifies every original detail HTML hash, source URL, stable selection seed and contiguity; duplicate or missing URLs cause a hard failure. It preserves the source population, original incident IDs and direct URLs.

Per original case the research matrix contains MTBS and NIFC identifiers, CAL FIRE detail name/start day and unlocalized start-clock text, CAL FIRE annual-versus-detail county text, source-report acreage, descriptive original-source name signals, and the MTBS-vs-CAL-FIRE **retrospective** date comparison. Available source location coordinates are compared with the mapped MTBS centroid and spatial vicinity of the original NIFC polygon. These are descriptive historical clues, NOT an independent event identity, verified ignition point, nonfire observation or wildfire forecast-performance metric.

Cases with multiple CAL FIRE page leads remain many-to-many research questions, not forced single matches. Cases with no lead remain unknown, never fire-negative. CAL FIRE and NIFC may share upstream government incident records. Complete capture of *candidate-linked URLs* does not establish a census of California fires or independent validation.

Outputs: SHA-256-linked JSON, spreadsheet-formula-safe CSV, and escaped/CSP-restricted offline HTML; all new-only outside original source evidence directories. The fixed real-data CI run now captures the 18 source pages in three six-page batches and checks full coverage with bounded evidence archived for seven days.

**Research maturity:** experimental historical source comparison. Verified same-fire crosswalks: 0. Verified nonfire samples: 0. Calibrated forecast accuracy: not measured.
