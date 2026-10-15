"""Recount verified FIRMS originals with unresolved recurrent bins kept explicit.

This is a positive-only descriptive sensitivity, not a corrected fire time series.
The recurrence rule supplies review candidates; no bin is removed as a confirmed
non-wildfire source without separate physical-source evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

from .annual_country_analytics import (_acquisition, _asset_path, _validate_manifest,
                                       MAX_SELECTED_PIXELS, PIXEL_FIELDS, SOURCES)
from .historical_rollup import _bytes
from .observational_cohort import validate_regions
from .region_diagnostics import distance_km
from .spatial_recurrence import _bin_key


def _verified_spatial(spatial: dict, regions: list[dict], manifest: dict) -> tuple[str, dict]:
    source = dict(spatial)
    digest = source.pop('evidence_sha256', None)
    if (not isinstance(digest, str) or hashlib.sha256(_bytes(source)).hexdigest() != digest
        or source.get('status') != 'descriptive_spatial_recurrence_only'
        or source.get('grid_degrees_wgs84') != 0.01
        or source.get('independent_static_source_evidence') is not False
        or source.get('observation_opportunity_verified') is not False
        or source.get('no_detection_count') is not None
        or [item['region'] for item in source.get('regions', [])] != regions):
        raise ValueError('spatial source report hash or region contract differs')
    assets = {(item['year'], item['provider']): item['sha256'] for item in manifest['thermal_assets']}
    if assets != {(item['year'], item['provider']): item['sha256'] for item in source['source_asset_manifest']}:
        raise ValueError('spatial report original asset hashes differ')
    return digest, {item['region']['region_id']: item for item in source['regions']}


def build_sensitivity(manifest: dict, regions: list[dict], spatial: dict,
                      raw_dir: str | Path) -> dict:
    """Stream the six SHA-pinned country files and separate unresolved-bin pixels."""
    _, _, years = _validate_manifest(manifest)
    chosen = validate_regions(regions)
    spatial_hash, spatial_by_region = _verified_spatial(spatial, chosen, manifest)
    unresolved = {}
    for region in chosen:
        item = spatial_by_region[region['region_id']]
        bins = {row['bin_id'] for row in item['published_bins']
                if row['classification'] == 'potential_static_thermal_source'
                and row['independently_classified'] is False
                and row['source_identity_status'] == 'unresolved'}
        if len(bins) != item['potential_static_source_bins']:
            raise ValueError('unpublished or independently classified recurrent bin')
        unresolved[region['region_id']] = bins
    raw_dir = Path(raw_dir)
    if raw_dir.is_symlink() or not raw_dir.is_dir():
        raise ValueError('original NASA file directory missing')
    counts = Counter()
    population = Counter()
    with tempfile.TemporaryDirectory(prefix='ws-static-sensitivity-') as temporary:
        with closing(sqlite3.connect(Path(temporary) / 'fingerprints.sqlite3')) as db:
            db.execute('CREATE TABLE rows(asset INTEGER,digest TEXT,PRIMARY KEY(asset,digest))')
            for index, asset in enumerate(sorted(manifest['thermal_assets'],
                                                  key=lambda item: (item['year'], item['provider']))):
                path = _asset_path(raw_dir, asset)
                provider, year = asset['provider'], asset['year']
                with path.open(newline='', encoding='utf-8') as handle:
                    reader = csv.DictReader(handle)
                    if not PIXEL_FIELDS <= set(reader.fieldnames or []):
                        raise ValueError('NASA source schema differs')
                    for row in reader:
                        population['country_source_rows'] += 1
                        _acquisition(row, year, SOURCES[provider][1])
                        digest = hashlib.sha256(_bytes({key: row[key] for key in PIXEL_FIELDS})).hexdigest()
                        if not db.execute('INSERT OR IGNORE INTO rows VALUES(?,?)', (index, digest)).rowcount:
                            population['duplicate_source_rows'] += 1
                            continue
                        lat, lon = float(row['latitude']), float(row['longitude'])
                        for region in chosen:
                            if distance_km(lat, lon, region['latitude'], region['longitude']) > region['radius_km']:
                                continue
                            population['selected_raw_pixels'] += 1
                            if population['selected_raw_pixels'] > MAX_SELECTED_PIXELS:
                                raise ValueError('selected raw pixels exceed research bound')
                            region_id = region['region_id']
                            key = (region_id, year, provider)
                            is_unresolved = ':'.join(map(str, _bin_key(lat, lon))) in unresolved[region_id]
                            counts[key, 'all'] += 1
                            counts[key, 'type2'] += row['type'] == '2'
                            if is_unresolved:
                                counts[key, 'unresolved'] += 1
                                counts[key, 'unresolved_type2'] += row['type'] == '2'
                            break
    if (population['country_source_rows'] != spatial['population']['country_source_rows']
        or population['duplicate_source_rows'] != spatial['population']['duplicate_source_rows']
        or population['selected_raw_pixels'] != spatial['population']['selected_raw_pixels']):
        raise ValueError('source population differs from spatial report')
    population.setdefault('duplicate_source_rows', 0)
    population['source_files'] = len(manifest['thermal_assets'])
    output_regions = []
    for region in chosen:
        region_id = region['region_id']
        sensor_rows = []
        for year in years:
            source_year = next(item for item in spatial_by_region[region_id]['yearly_quality_rows']
                               if item['year'] == year)
            for provider in sorted(SOURCES):
                key = (region_id, year, provider)
                all_pixels = counts[key, 'all']
                if all_pixels != source_year['provider_counts'].get(provider, 0):
                    raise ValueError('year/sensor count differs from verified spatial report')
                unresolved_pixels = counts[key, 'unresolved']
                sensor_rows.append({'year': year, 'provider': provider,
                                    'all_raw_pixels': all_pixels,
                                    'unresolved_recurrent_raw_pixels': unresolved_pixels,
                                    'other_raw_pixels': all_pixels - unresolved_pixels,
                                    'all_source_type2_raw_pixels': counts[key, 'type2'],
                                    'unresolved_source_type2_raw_pixels': counts[key, 'unresolved_type2'],
                                    'independently_excluded_raw_pixels': 0})
        all_pixels = sum(row['all_raw_pixels'] for row in sensor_rows)
        unresolved_pixels = sum(row['unresolved_recurrent_raw_pixels'] for row in sensor_rows)
        if all_pixels != spatial_by_region[region_id]['selected_raw_pixels']:
            raise ValueError('selected region population differs')
        output_regions.append({'region_id': region_id, 'all_raw_pixels': all_pixels,
                               'unresolved_recurrent_bins': sorted(unresolved[region_id]),
                               'unresolved_recurrent_raw_pixels': unresolved_pixels,
                               'other_raw_pixels': all_pixels - unresolved_pixels,
                               'independently_excluded_raw_pixels': 0,
                               'year_sensor_rows': sensor_rows})
    report = {'schema_version': 1, 'status': 'unresolved_static_source_sensitivity_only',
              'spatial_report_sha256': spatial_hash,
              'source_asset_manifest': spatial['source_asset_manifest'],
              'population': dict(population), 'regions': output_regions,
              'grid_degrees_wgs84': 0.01, 'unresolved_bins_not_excluded': True,
              'independent_nonwildfire_source_count': 0,
              'observation_opportunity_verified': False, 'fire_rate_comparison_supported': False,
              'interpretation': 'All original thermal candidates remain counted. The separate unresolved recurrence subset is a sensitivity view, not a confirmed industrial-source exclusion. Other pixels are also unverified candidates. No acquisition denominator, independent non-wildfire identification or fire-rate trend is available.'}
    report['evidence_sha256'] = hashlib.sha256(_bytes(report)).hexdigest()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--regions-json', type=Path, required=True)
    parser.add_argument('--spatial', type=Path, required=True)
    parser.add_argument('--raw-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = build_sensitivity(json.loads(args.manifest.read_text()),
                               json.loads(args.regions_json.read_text()),
                               json.loads(args.spatial.read_text()), args.raw_dir)
    args.output.write_bytes(_bytes(report))
    print(json.dumps({'population': report['population'], 'evidence_sha256': report['evidence_sha256']}))


if __name__ == '__main__':
    main()
