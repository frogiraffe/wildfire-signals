"""Bounded official CAL FIRE FRAP perimeter evidence; no fire-negative labels.

This is a retrospective source-evidence cohort in a fixed Sacramento-area box.
Final perimeters are not ignition locations, prospective labels or a complete
record of fires. GPS collection documents geometry method, not how an event was
first discovered or independence of its agency record from every other source.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlencode

from .historical_rollup import _bytes


GEO_SHA = '99ec874041ea1847fea4b14628be052ee1c5c4ab680ecc90e774cca7c015ae70'
META_SHA = '1ed42c91954cd7d4232a4862943bcab56f94d287b7ae773f18b6827f63333e04'
COUNT_SHA = '77225c1b889e1a23d33f5e7724a89deba869a0b481aff9fe90736b56532d0542'
LAYER = 'https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/California_Historic_Fire_Perimeters/FeatureServer/0'
BBOX = [-121.88, 38.45, -121.31, 38.95]
FIELDS = 'OBJECTID,GlobalID,YEAR_,FIRE_NAME,ALARM_DATE,CONT_DATE,AGENCY,C_METHOD,OBJECTIVE,GIS_ACRES,IRWINID,COMMENTS'
QUERY = LAYER + '/query?' + urlencode({
    'where': 'YEAR_ >= 2023 AND YEAR_ <= 2025',
    'geometry': ','.join(str(x) for x in BBOX),
    'geometryType': 'esriGeometryEnvelope', 'inSR': '4326',
    'spatialRel': 'esriSpatialRelIntersects', 'outFields': FIELDS,
    'returnGeometry': 'true', 'outSR': '4326', 'orderByFields': 'OBJECTID ASC',
    'resultRecordCount': '100', 'f': 'geojson'})
METADATA_URL = LAYER + '?f=json'
COUNT_QUERY = LAYER + '/query?' + urlencode({
    'where': 'YEAR_ >= 2023 AND YEAR_ <= 2025',
    'geometry': ','.join(str(x) for x in BBOX),
    'geometryType': 'esriGeometryEnvelope', 'inSR': '4326',
    'spatialRel': 'esriSpatialRelIntersects', 'returnCountOnly': 'true', 'f': 'json'})
RIGHTS = 'https://publish.data.ca.gov/dataset/california-fire-perimeters-all'


def _vertices(geometry: dict):
    coordinates = geometry.get('coordinates')
    polygons = coordinates if geometry['type'] == 'MultiPolygon' else [coordinates]
    if not isinstance(polygons, list) or not polygons:
        raise ValueError('empty perimeter geometry')
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise ValueError('empty perimeter polygon')
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError('perimeter ring not closed')
            for point in ring:
                if not isinstance(point, list) or len(point) < 2 or any(type(x) not in (int, float) for x in point[:2]):
                    raise ValueError('invalid GeoJSON vertex')
                lon, lat = point[:2]
                if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
                    raise ValueError('perimeter vertex outside WGS84')
                yield lon, lat


def _day(value: object) -> str | None:
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('invalid source date')
    return datetime.fromtimestamp(value / 1000, timezone.utc).date().isoformat()


def build_cohort(geo_bytes: bytes, metadata_bytes: bytes, count_bytes: bytes, *,
                 verify_source_hashes: bool = True) -> dict:
    if (not 0 < len(geo_bytes) <= 1_000_000 or not 0 < len(metadata_bytes) <= 200_000
        or not 0 < len(count_bytes) <= 1000):
        raise ValueError('bounded original FRAP sources required')
    geo_hash, meta_hash = hashlib.sha256(geo_bytes).hexdigest(), hashlib.sha256(metadata_bytes).hexdigest()
    count_hash = hashlib.sha256(count_bytes).hexdigest()
    if verify_source_hashes and (geo_hash != GEO_SHA or meta_hash != META_SHA or count_hash != COUNT_SHA):
        raise ValueError('original FRAP source SHA-256 differs')
    source = json.loads(geo_bytes)
    metadata = json.loads(metadata_bytes)
    count = json.loads(count_bytes).get('count')
    if (source.get('type') != 'FeatureCollection' or source.get('exceededTransferLimit') is True
        or not isinstance(source.get('features'), list) or type(count) is not int
        or count != 9 or len(source['features']) != count
        or metadata.get('name') != 'California Fire Perimeters (all)'
        or metadata.get('geometryType') != 'esriGeometryPolygon'
        or metadata.get('maxRecordCount', 0) < 100):
        raise ValueError('FRAP layer or bounded source population differs')
    domains = {field['name']: {item['code']: item['name'] for item in field.get('domain', {}).get('codedValues', [])}
               for field in metadata['fields'] if field['name'] in ('C_METHOD', 'OBJECTIVE')}
    if (domains.get('C_METHOD', {}).get(1) != '1 - GPS Ground'
        or domains['C_METHOD'].get(2) != '2 - GPS Air'
        or domains.get('OBJECTIVE', {}).get(1) != 'Suppression (Wildfire)'):
        raise ValueError('FRAP evidence codes changed')
    cases, seen, seen_objects = [], set(), set()
    for feature in source['features']:
        attrs, geometry = feature.get('properties'), feature.get('geometry')
        if not isinstance(attrs, dict) or not isinstance(geometry, dict) or geometry.get('type') not in ('Polygon', 'MultiPolygon'):
            raise ValueError('invalid FRAP feature')
        identifier = attrs.get('GlobalID')
        object_id = attrs.get('OBJECTID')
        if (not isinstance(identifier, str) or identifier in seen or not identifier
            or type(object_id) is not int or object_id in seen_objects):
            raise ValueError('missing or duplicate FRAP GlobalID')
        seen.add(identifier)
        seen_objects.add(object_id)
        coords = list(_vertices(geometry))
        if len(coords) < 4:
            raise ValueError('perimeter has too few vertices')
        west, south = min(x for x, _ in coords), min(y for _, y in coords)
        east, north = max(x for x, _ in coords), max(y for _, y in coords)
        if east < BBOX[0] or west > BBOX[2] or north < BBOX[1] or south > BBOX[3]:
            raise ValueError('perimeter does not intersect study query envelope')
        year, method, objective = attrs.get('YEAR_'), attrs.get('C_METHOD'), attrs.get('OBJECTIVE')
        alarm = _day(attrs.get('ALARM_DATE'))
        if (year not in (2023, 2024, 2025) or (alarm and not alarm.startswith(str(year)))
            or method not in domains['C_METHOD'] or
            (objective is not None and objective not in domains['OBJECTIVE'])):
            raise ValueError('FRAP year, date or source code differs')
        grounded = method in (1, 2) and objective == 1 and alarm is not None
        cases.append({'source_global_id': identifier, 'source_object_id': attrs.get('OBJECTID'),
                      'source_name': attrs.get('FIRE_NAME'), 'source_agency': attrs.get('AGENCY'),
                      'source_irwin_id': attrs.get('IRWINID'), 'source_year': year,
                      'source_alarm_date_calendar': alarm,
                      'source_containment_date_calendar': _day(attrs.get('CONT_DATE')),
                      'source_method_code': method, 'source_method': domains['C_METHOD'][method],
                      'source_objective_code': objective, 'source_objective': domains['OBJECTIVE'].get(objective),
                      'source_gis_acres': attrs.get('GIS_ACRES'),
                      'geometry_type': geometry['type'], 'geometry_bounds_wgs84': [west, south, east, north],
                      'evidence_status': 'ground_or_air_mapped_suppression_perimeter' if grounded
                          else 'agency_perimeter_independence_unresolved',
                      'geometry_method_distinct_from_FIRMS_hotspot_pixels': grounded,
                      'event_ascertainment_independence_verified': False,
                      'geometry_is_ignition_point': False, 'decision_time_available': False,
                      'fire_negative': False})
    cases.sort(key=lambda row: (row['source_year'], row['source_object_id']))
    positives = sum(row['evidence_status'] == 'ground_or_air_mapped_suppression_perimeter' for row in cases)
    report = {'schema_version': 1, 'status': 'retrospective_agency_perimeter_evidence_only',
              'study_bbox_wgs84': BBOX, 'study_years': [2023, 2024, 2025],
              'source_query_url': QUERY, 'source_metadata_url': METADATA_URL,
              'source_count_query_url': COUNT_QUERY,
              'source_rights_url': RIGHTS, 'source_revision': 'firep25_1 (April 2026)',
              'source_geojson_sha256': geo_hash, 'source_metadata_sha256': meta_hash,
              'source_count_sha256': count_hash,
              'source_first_available_at': None, 'source_geometry_resolution': 'varies by collection method',
              'cases': cases,
              'population': {'source_perimeters': len(cases),
                             'ground_or_air_suppression_evidence': positives,
                             'other_method_or_objective_unknown': len(cases) - positives,
                             'verified_negative_outcomes': 0,
                             'unlisted_cell_dates_with_verified_negative': 0},
              'independent_event_ascertainment_verified': False,
              'complete_fire_outcome_coverage': False, 'satellite_cell_exposure_verified': False,
              'occurrence_model_eligible': False,
              'interpretation': 'Official final mapped perimeters provide geolocated retrospective agency evidence. Five have GPS ground/air geometry and wildfire suppression objective, but the event discovery lineage is not verified. Four have imagery methods and/or missing objective. Perimeter geometry is not ignition location or prospective availability. Omission from the thresholded, incomplete layer is unknown, never a fire-negative.'}
    report['evidence_sha256'] = hashlib.sha256(_bytes(report)).hexdigest()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geojson', type=Path, required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--count', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = build_cohort(args.geojson.read_bytes(), args.metadata.read_bytes(), args.count.read_bytes())
    args.output.write_bytes(_bytes(report))
    print(json.dumps({'population': report['population'], 'evidence_sha256': report['evidence_sha256']}))


if __name__ == '__main__':
    main()
