# Historical multi-source context — agency + FIRMS archive + captured NWS

This end-to-end addition extends the already-working **offline Historical Intelligence Workbench**, rather than creating a parallel service or expensive global data pipeline. All inputs are user-held **historical archives**. The report does not download satellite or weather data, publish to Cloudflare, or compute wildfire predictions.

## Generate an as-of joined report

First populate the agency archive using the previously documented checksum-verified agency receipt workflow. NASA FIRMS candidates may already be present in the same HistoryStore from `archive_snapshot`. A separate optional NWS HistoryStore can be generated using the existing `fire_public.weather_pilot`. Keep raw files and SQLite databases outside the public repository.

```bash
python -m fire_public.intelligence_workbench report \
  --db /private/research/agency-and-satellite.sqlite3 \
  --weather-db /private/research/weather.sqlite3 \
  --at 2026-10-12T10:00:00Z \
  --latitude 39.7456 --longitude -97.0892 --radius-km 100 \
  --satellite-hours 72 \
  --json /private/reports/decision-evidence.json \
  --html /private/reports/decision-evidence.html
```

The `--weather-db` argument is optional. Without it, the report contains independent agency and archived satellite candidate evidence. The CLI's `--satellite-hours` accepts 6, 24 or 72.

## What is measured

**Satellite:** bounded (max 50,000 newest eligible archive rows) selection of archived satellite candidates within the selected globe circle and lookback. Repeated re-captures of one candidate ID and observation timestamp are deduplicated; distinct spatial cells and cells observed in more than one UTC hour are shown. Sensor memberships and missing-location counts are reported. The data window and capture time are both checked against the selected as-of cutoff. This is not an independent fire count.

**Weather:** if requested, read at most 2,000 latest archived NWS `weather_forecast_snapshot` records known by the selected decision time, search at most 5 km from each event location, and require recorded forecast source update time and valid time of essential fields to cover the instant. Show actual recorded wind speed, direction, temperature, humidity and other available fields alongside the source issue/capture/validity times and grid point distance. If no eligible weather exists, display an explicit missing-context status instead of a numerical zero. The 5 km distance threshold is contextual proximity, **not** a proof the grid forecast describes fire-site conditions.

**Agency:** as before, display only provider records captured by that time, with event identity, status, receipt completeness, outages and provenance. A candidate close to an agency incident is never promoted to a confirmed wildfire; absence from a complete active layer is not an extinguishment outcome.

## Reproducibility and scope

This pipeline works for **geospatially selected worldwide historical agency and satellite records that actually exist in the local archive**. Currently the optional weather adapter uses US NWS forecasts only. It must not claim worldwide weather coverage or a globally calibrated risk model. Additional international sources should adopt the same receipt-time, spatial-offset and validity-window contract with provider-specific licensing and units.

The integrated HTML report is portable, no-JavaScript, escaped, and viewable offline. Full evidence remains available in JSON. Query caps produce explicit truncation warnings rather than fabricated completeness.

## Validation

```bash
python -m unittest discover -s tests -p 'test_historical_context.py' -v
python -m unittest discover -s tests -p 'test_intelligence_workbench.py' -v
python -m unittest discover -s tests -p 'test_decision_evidence.py' -v
```

CI tests the real SQLite schema, source captured-at cutoff, antimeridian, distinct cell-hours, latest eligible NWS forecast, invalid/outdated grid intervals, missing event coordinates, JSON/HTML CLI round-trip, and legacy archive compatibility.

**Not yet:** confirmed wildfire ground truth, calibrated occurrence probabilities, spread simulations, sensor detection completeness audit, or continuously archived international weather. Those require independent, versioned source evidence and evaluation.
