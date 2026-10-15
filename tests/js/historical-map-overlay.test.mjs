import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {archivedGeojson,historicalStudyUrl,STUDIES} from '../../public/historical-map-overlay.mjs';
const source=JSON.parse(await readFile(new URL('../../public/data/turkey-spatial-recurrence-2023-2025.json',import.meta.url),'utf8'));
test('valid published WGS84 cells become source-consistent polygons',()=>{
 const fc=archivedGeojson(source,'ANTALYA_25KM');
 assert.equal(fc.type,'FeatureCollection');
 assert.ok(fc.features.length>0);
 const p=fc.features[0];
 assert.equal(p.geometry.type,'Polygon');
 assert.deepEqual(p.geometry.coordinates[0][0],p.geometry.coordinates[0][4]);
 assert.equal(p.properties.sourceIdentity,'unresolved');
 assert.ok(p.properties.pixels>0);
});
test('satellite filtering excludes cells without source rows, not inferred fire negatives',()=>{
 const study='DALAMAN_25KM';
 const all=archivedGeojson(source,study);
 const noaa=archivedGeojson(source,study,'VIIRS_NOAA20_STANDARD');
 const snpp=archivedGeojson(source,study,'VIIRS_SNPP_STANDARD');
 assert.ok(noaa.features.length<=all.features.length);
 assert.ok(snpp.features.length<=all.features.length);
 assert.equal(source.observation_opportunity_verified,false);
 assert.equal(source.independent_fire_outcome_valid,false);
 assert.match(historicalStudyUrl(study),/study=DALAMAN_25KM/);
 assert.equal(STUDIES[study].lon,28.7925);
});
test('invalid selections rejected without fallback to invented area',()=>{
 assert.throws(()=>archivedGeojson(source,'UNKNOWN'),/Invalid/);
 assert.throws(()=>historicalStudyUrl('UNKNOWN'),/Unknown study/);
 assert.throws(()=>archivedGeojson(source,'ANTALYA_25KM','VIIRS_UNKNOWN'),/Invalid/);
});