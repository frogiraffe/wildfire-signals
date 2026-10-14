"""Two-day standard VIIRS catalog and outcome-readiness audit, never an exposure mask.

The source snapshot contains original public CMR response bodies. Their bounding-box
polygons and intervals establish catalog context only; no L1/L2 pixels are inspected.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode

from .historical_rollup import _bytes
from .observation_opportunity import classify_interval


START, END = '2025-01-06', '2025-01-07'
BBOX = '30.5,36.6,31.1,37.2'
PRODUCTS = (('VJ103IMG', '2.1', '-LAADS'), ('VJ114IMG', '002', '-LPCLOUD'))
CMR = 'https://cmr.earthdata.nasa.gov/search/granules.json'


def _expected_url(product: str, version: str) -> str:
    return CMR + '?' + urlencode({
        'short_name': product, 'version': version,
        'temporal': '2025-01-06T00:00:00Z,2025-01-08T00:00:00Z',
        'bounding_box': BBOX, 'page_size': '100'})


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError('granule and candidate times must be UTC')
    return parsed


def _annual(annual: dict) -> tuple[list[dict], str]:
    value = dict(annual)
    digest = value.pop('evidence_sha256', None)
    if (value.get('status') != 'retrospective_standard_archive_exploration'
        or value.get('region', {}).get('region_id') != 'ANTALYA_25KM'
        or value.get('observation_opportunity_verified') is not False
        or not isinstance(digest, str)
        or hashlib.sha256(_bytes(value)).hexdigest() != digest):
        raise ValueError('annual research evidence hash or contract differs')
    rows = [row for row in value['candidate_provider_hours']
            if START <= row['observed_hour'][:10] <= END
            and row['provider'] == 'VIIRS_NOAA20_STANDARD']
    return rows, digest


def build_report(snapshot: dict, annual: dict) -> dict:
    """Validate original CMR responses and compare catalog intervals to archived positives."""
    if snapshot.get('schema_version') != 1 or len(snapshot.get('queries', [])) != 2:
        raise ValueError('bounded standard CMR source snapshot required')
    _utc(snapshot['fetched_at'])
    candidates, annual_hash = _annual(annual)
    intervals, queries = {}, []
    for query, (product, version, provider_suffix) in zip(snapshot['queries'], PRODUCTS, strict=True):
        body = query.get('body')
        if (query.get('product') != product or query.get('url') != _expected_url(product, version)
            or not isinstance(body, str)
            or hashlib.sha256(body.encode()).hexdigest() != query.get('response_sha256')):
            raise ValueError('CMR product, query or original response hash differs')
        entries = json.loads(body).get('feed', {}).get('entry', [])
        if type(query.get('cmr_hits')) is not int or not 0 <= query['cmr_hits'] <= 100 or len(entries) != query['cmr_hits']:
            raise ValueError('CMR hits or page completeness differs')
        seen = set()
        for entry in entries:
            identifier = entry.get('id')
            first, last = _utc(entry['time_start']), _utc(entry['time_end'])
            if (not isinstance(identifier, str) or identifier in seen
                or not identifier.endswith(provider_suffix)
                or not entry.get('collection_concept_id', '').endswith(provider_suffix)
                or not entry.get('producer_granule_id', '').startswith(product + '.')
                or not entry.get('polygons') or first >= last
                or first.date().isoformat() > END or last.date().isoformat() < START):
                raise ValueError('CMR granule identity, interval or search footprint invalid')
            seen.add(identifier)
            intervals.setdefault((first.isoformat(), last.isoformat()), {})[product] = identifier
        queries.append({'product': product, 'version': version,
                        'provider': provider_suffix[1:], 'cmr_hits': query['cmr_hits'],
                        'url': query['url'], 'response_sha256': query['response_sha256']})
    paired = [dict(start_at=start, end_at=end, geolocation_granule_id=items.get('VJ103IMG'),
                   active_fire_granule_id=items.get('VJ114IMG'),
                   catalog_pair_status='both_catalogued' if len(items) == 2 else 'single_product')
              for (start, end), items in sorted(intervals.items())]
    daily = []
    for day in (START, END):
        selected = [row for row in candidates if row['observed_hour'].startswith(day)]
        minutes = []
        for row in selected:
            observed = _utc(row['first_candidate_minute'])
            matches = [item for item in paired if
                       _utc(item['start_at']) <= observed < _utc(item['end_at'])]
            minutes.append({'observed_minute': row['first_candidate_minute'],
                            'raw_pixels': row['raw_pixels'],
                            'catalog_pair_status': 'both_catalogued' if any(
                                item['catalog_pair_status'] == 'both_catalogued' for item in matches)
                            else 'not_paired'})
        daily.append({'date_utc': day, 'archived_noaa20_pixels': sum(row['raw_pixels'] for row in selected),
                      'positive_sensor_hours': len(selected), 'candidate_minutes': minutes,
                      'catalogued_paired_intervals': sum(item['catalog_pair_status'] == 'both_catalogued'
                          and item['start_at'].startswith(day) for item in paired),
                      'observation_state': classify_interval(
                          archived_candidates=sum(row['raw_pixels'] for row in selected),
                          retrieval='complete', acquisition='unknown'),
                      'cell_observation_verified': False,
                      'no_reported_detection_count': None})
    gates = {
        'defined_outcome_and_horizon': False,
        'verified_cell_exposure': False,
        'independent_positive_outcomes': False,
        'independent_negative_outcomes': False,
        'decision_time_environment_availability': False,
        'temporal_and_geographic_evaluation_cohort': False,
    }
    report = {'schema_version': 1, 'status': 'standard_catalog_and_model_readiness_only',
              'region': 'ANTALYA_25KM', 'start_date': START, 'end_date': END,
              'bbox_wgs84': BBOX, 'cmr_fetched_at': snapshot['fetched_at'],
              'cmr_snapshot_sha256': hashlib.sha256(_bytes(snapshot)).hexdigest(),
              'annual_report_sha256': annual_hash, 'source_queries': queries,
              'product_intervals': paired, 'daily_rows': daily,
              'population': {'geolocation_granules': queries[0]['cmr_hits'],
                             'active_fire_granules': queries[1]['cmr_hits'],
                             'paired_intervals': sum(row['catalog_pair_status'] == 'both_catalogued' for row in paired),
                             'archived_noaa20_pixels': sum(row['archived_noaa20_pixels'] for row in daily)},
              'granule_contents_inspected': False, 'cell_exposure_verified': False,
              'no_detection_count': None, 'independent_fire_outcome_valid': False,
              'model_readiness': {'gates': gates, 'scientific_comparison_eligible': all(gates.values()),
                                  'operational_prediction_eligible': False, 'models_trained': 0},
              'interpretation': 'CMR search-box granules and exact paired intervals are catalog evidence only. They do not establish valid acquisition, cloud/quality, or L2 fire-mask result at a cell. No archived row on 2025-01-07 is not a no-detection or no-fire observation. Agency and EFFIS sources have not established independent location/date positives and covered negatives for this cohort.'}
    report['evidence_sha256'] = hashlib.sha256(_bytes(report)).hexdigest()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--annual', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = build_report(json.loads(args.snapshot.read_text()), json.loads(args.annual.read_text()))
    args.output.write_bytes(_bytes(report))
    print(json.dumps({'output': str(args.output), 'population': report['population'],
                      'evidence_sha256': report['evidence_sha256']}))


if __name__ == '__main__':
    main()
