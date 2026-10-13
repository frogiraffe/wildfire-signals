# CAL FIRE alternative-event ambiguity dossiers (2018 research pilot)

The original Northern California 2018 study had 14 NIFC–MTBS geographic candidate pairs and 18 fully archived, name-linked CAL FIRE incident-detail URLs. Seven candidate cases contained multiple CAL FIRE page possibilities; five had one and two had no name lead. These dossiers support human examination of **alternative original historical records** without automatic same-fire identity assignment.

## Generate the source-replayed casebooks

First download the original source research artifacts or locally rerun the established authentic NIFC, MTBS, CAL FIRE annual and full incident-detail capture workflow. Original inputs must be complete and unchanged. Then:

    python -m fire_public.calfire_ambiguity_dossiers \
      --study-dir /private/wildfire/california-2018 \
      --calfire-archive-dir /private/wildfire/calfire-2018 \
      --batch /private/wildfire/calfire-detail-batch-0 \
      --batch /private/wildfire/calfire-detail-batch-6 \
      --batch /private/wildfire/calfire-detail-batch-12 \
      --output-dir /private/wildfire/ambiguity-dossiers

The tool **replays original source bytes before deriving any claim**. It rechecks NIFC/MTBS polygons and points, CAL FIRE annual source HTML, all candidate-linked URLs, each original incident page SHA-256, deterministic selection seed and non-overlapping batch offsets. Source drift, an omitted source page or modified derived report fails closed. This report phase makes no external network requests.

It writes three new-only files outside source archives: ambiguity-dossiers.json (machine-readable candidate/alternative-source claims and evidence gaps), ambiguity-dossiers.csv (formula-injection-safe source comparisons) and ambiguity-dossiers.html (responsive offline casebook, source-escaped HTML, restrictive no-script/no-network Content Security Policy and direct official links).

## Case-by-case research evidence

Every NIFC–MTBS candidate retains original source IDs, original MTBS type and retrospective day, and each alternative CAL FIRE incident URL/source page hash. The workbench shows name, start day and unspecified-timezone source clock, county, reported acreage, available source location and its distance to the MTBS mapped centroid, plus proximity to the original NIFC perimeter. None of these coordinates is proven to be a historical ignition position.

For every pair of **alternative CAL FIRE pages within a candidate case**, the report calculates absolute retrospective start-day gaps and separation between the two *displayed source locations* (if both exist). It also records normalized-name equality, distinct official URLs and **reuse of one official CAL FIRE page by multiple different NIFC–MTBS candidate pairs**. These are descriptive evidence investigations, not fire identity confidence or Bayesian match probabilities.

All cases list the actual evidence still missing: independently authenticated original source incident IDs, a source-lineage audit, separate human adjudication, an established NIFC ignition day, and geographic source semantics. Several alternative URLs can belong to different reported event definitions; forcing a one-to-one join would erase ambiguity.

Missing CAL FIRE name hits are unknown, never observed nonfire. Calendar-day agreement, name overlap, geographic nearness and shared government agency data **do not prove that the two sources observe an independently confirmed same physical wildfire**. Neither CAL FIRE nor NIFC proves independent source lineage by being a third government webpage. An original source timestamp may be retrospective and cannot silently be used as decision-time feature data.

## Real CI and limits

The full original source CI now generates these three static report outputs from the actual 2018 NIFC + MTBS + CAL FIRE archive and all 18 actual individual incident pages, alongside the existing full-source matrix. Its checks require the correct total candidate count, fully covered incident detail sources, consistent numbers of alternatives, verified zero crosswalks and zero independent fire absence observations.

The offline unit suite uses synthetic source examples and explicitly asserts tampered-source refusal, alternative link multiplicity, date comparisons, safe output, no false confidence and deterministic operation.

Scientific maturity: **experimental retrospective source evidence**. Verified same-fire crosswalks: 0. Independently observed true negatives: 0. Measured wildfire forecast skill: none. The wider global wildfire product remains separate from this US-limited historical validation pilot.
