# Wildfire Signals — Global Product & Engineering Policy

Status: active engineering guidance. Product vision is in `docs/wildfire-analysis-product-vision-2026-10-12.md`. This policy defines *how* to implement it, not proof of delivered functionality.

## Mission and worldwide coverage
Develop a worldwide wildfire evidence and analysis platform. US, Canada, and Türkiye are initial validation regions, **not a permanent geographic whitelist**. Satellite observations may have global coverage; independent agency confirmation, perimeter history, weather, terrain, fuels, labels, and model validation will vary by geography. Never equate global map visibility with global validated wildfire detection or forecasts. Support international coordinate systems normalized to WGS84, antimeridian crossing, polar edge cases, UTC event timestamps, local display time zones, source licensing, languages, and region-specific metadata. Prefer extensible provider registries and geographic capabilities/coverage manifests over country-specific conditions. Show coverage gaps transparently.

## Core execution rule
**Inspect → select a bounded vertical slice → implement → test → evaluate → report.**
Prioritize working code over repeated feasibility studies and planning-only output. For implementation requests, do not end at an audit if a meaningful safe subset can be built. Treat uncertain research findings as reasons to **scope and label experiments**, not automatic prohibitions on implementation.

## Maturity tiers
1. Exploratory: simulated or fixture-based method; no empirical validity claim.
2. Experimental: executable real-data pilot with identified limitations and reproducible outputs.
3. Validated: independently evaluated against defined baselines and appropriate temporal/geographic holdouts, with calibration where relevant.
4. Production: validated plus deployment, safety, performance, rollback, observability and cost gates.

Never silently promote a result between tiers. Keep experimental outputs separate from public decision guidance.

## Delegated engineering autonomy
Allowed without repeated permission: reversible feature-branch changes, refactoring, tests, local bounded experiments, documented open data adapters, reproducible model baselines, UI prototypes, and code cleanup. Ask before paid resources, new privileged accounts/secrets, exposing private data, destructive operations, or consequential production deployments. Never force-push main or delete user branches without authorization. Existing main branch and live collector are protected; prefer reviewed PRs. Avoid running unnecessary Docker services or leaving processes active.

## Science and evidence
Keep `satellite_candidate`, `agency_incident`, actual event identity, final burned-area estimates, observed perimeter, and predicted/simulated future perimeter semantically distinct. A geospatial proximity match is not independent fire validation. Record observation time, publication/issue time, availability/receipt time, valid time, source status, license, coordinate reference, resolution, uncertainty and corrections. Distinguish outage/no coverage from genuine no observation. Set a precisely defined target and horizon before forecasting. Avoid temporal, event-level and geographic leakage. Use simple historical/base-rate/persistence baselines before complex ML. Evaluate missingness, label censoring, false positives, false negatives, calibration and distribution shift. Never invent ground truth, measured performance or numerical risk estimates.

## Delivery priorities
1. Global coverage registry: coverage, data freshness, provenance, provider reliability and licensing per region/source.
2. Event identity and bounded historic evidence with as-of replay.
3. Weather, land cover, fuels, topography and perimeter features with timestamp/version contracts.
4. Reproducible descriptive analysis and baselines; then calibrated models when labels permit.
5. Investigation and scenario UI clearly distinguishing observed/experimental/validated.
6. Internationalization, accessible responsive mapping, and testable operational readiness.

These priorities may be reordered when evidence supports higher value. Avoid abstract platforms before the first useful complete slice.

## Anti-stagnation
Do not repeatedly rewrite the roadmap, request confirmation for reversible local edits, or postpone all software work pending global data completeness. If a dependency blocks full implementation, implement the largest independently testable piece, including fixtures and an explicit limitation. Do not substitute synthetic-data scores for real-data evidence. Avoid speculative complexity and duplicate documentation.

## Branch integration discipline
Inventory branches and open PRs; compare each against latest main. Branches with zero ahead commits are already contained: do not merge or overwrite them. For diverged branches, inspect exact changes and tests; reject accidental hardcoded locality or outdated assumptions. Cherry-pick, adapt, or omit functionality on a fresh integration branch. Never treat the newest timestamp as proof of best code. Run targeted tests and available CI before merging into main. Clearly state what was and was not integrated. Preserve other branches unless expressly authorized to delete.

## Definition of done
Report changed files, actual tests and outcomes, data source and sample, measurable functionality, operational impact, scientific maturity and remaining blockers. Only claim deployment/uptime after fresh checks. Include the next executable action, not just a future research list.
