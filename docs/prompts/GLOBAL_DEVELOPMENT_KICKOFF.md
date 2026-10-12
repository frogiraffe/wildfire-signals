# Codex implementation kickoff — Global Wildfire Signals

Read `AGENTS.md`, `docs/ENGINEERING_POLICY.md`, `docs/wildfire-analysis-product-vision-2026-10-12.md`, current code, tests and active branches. Treat documentation as intent; verify implementations and current CI independently.

You are a principal engineer, applied statistician, geospatial data engineer, and product engineer. Deliver **working, tested software**, not an audit-only response.

## First delivery: globally reusable regional diagnostics
The older `codex/region-diagnostic-20261012` branch includes a useful read-only 50-km satellite observation diagnostic, but hardcodes Merauke and Kepi. Preserve the useful concept without hardcoding named regions.

Implement a reusable region diagnostics module and manual GitHub Actions entry point that:
- Accepts explicit geographic selections, such as a latitude/longitude/radius and optional named polygon or bounding box when the existing infrastructure supports it; validate inputs.
- Handles longitude wrap/antimeridian and reasonable latitude bounds; use geodesic or documented spherical distance.
- Takes snapshots read-only from the existing evidence layer, without introducing extra FIRMS queries or KV writes.
- Reports region and window, observed candidate cell-hours, distinct spatial cells, multi-hour recurrence, recent counts, latest observed time, sensor membership, source errors and staleness; keep agency incidents distinct.
- Does not call regional candidate counts actual fires, severity, burned area or wildfire probability.
- Runs deterministically on recorded small fixtures, including zero observations, stale source, antimeridian and invalid inputs.
- Documents how to run locally and, if appropriate, from a manually triggered workflow.
- Avoids breaking existing global map and collection workflows, Free quotas or upstream availability.

Use the existing workflow where appropriate; extract logic to testable Python rather than enlarging a one-off inline workflow script.

## Subsequent roadmap
After the region diagnostic is complete and verified, implement one end-to-end historical event/as-of analysis slice with appropriate ground truth and an interpretable baseline. Keep worldwide-compatible provider/coverage contracts even if first validation samples are from the US or Canada. Add data-driven sources, not fabricated coverage. Model scoring must use event/time/geography-aware validation and report missing labels/uncertainty. If validation inputs are insufficient, ship the experimental component rather than claiming a forecast.

## Working rules
Inspect actual current state, select one bounded vertical slice, code, run tests, inspect results, fix defects and create a reviewed PR. Do not wait for approval for ordinary reversible work. Do not spend the entire task writing proposals. Preserve credentials, other private repositories, zero-charge infrastructure, existing hosted collector, and official-versus-satellite semantics. Do not publish unvalidated forecasts or claim live success without checking it.

## End of task report
State exactly which files were modified, what tests ran with results, actual data versus fixtures, reproducibility commands, whether CI passed, scientific maturity, remaining gaps and next executable increment.
