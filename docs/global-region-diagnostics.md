# Global region diagnostics (experimental)

The existing **Analyze recent public observations** GitHub Actions workflow accepts optional region inputs for a read-only circle summary. Run the workflow manually with both latitude and longitude; leaving both empty runs its original worldwide snapshot audit. The job retrieves previously retained Cloudflare KV snapshots and performs no FIRMS requests or writes.

| Input | Meaning |
| --- | --- |
| `latitude` | WGS84 center latitude, -90 to 90 |
| `longitude` | WGS84 center longitude, -180 to 180 |
| `radius_km` | Great-circle radius, >0 and <=20,000 km; default 50 |
| `window_hours` | Look-back from latest scan, >0 and <=168; default 24 |

The job emits `REGION_JSON` with candidate observations, distinct cells, repeated observed hours, sensor memberships, snapshot data status and source errors. The `ANALYSIS_JSON` global summary remains unchanged.

**Interpretation:** This reports satellite *candidate cell-hours*, not independently verified wildfires, burned area, perimeters, or risk. A stale or incomplete source may undercount observations. Source timestamps and report scope must accompany any downstream visualization.

Example selections:
- Antalya: latitude `36.9`, longitude `30.7`, radius `50`.
- South Pacific across the date line: latitude `0`, longitude `179.9`, radius `50`.
These coordinates are merely examples; functionality is not geographically restricted.

Run focused tests with:

```sh
python -m unittest discover -s tests -p 'test_region_diagnostics.py' -v
```

Implementation and checks: `fire_public/region_diagnostics.py` and `tests/test_region_diagnostics.py`. The code deliberately excludes future timestamps and handles the antimeridian; it is an exploratory diagnostic, not a validated global wildfire analysis product.
