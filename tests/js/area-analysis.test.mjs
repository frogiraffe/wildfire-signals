import test from 'node:test';
import assert from 'node:assert/strict';
import {summarizeArea} from '../../public/area-analysis.mjs';

const now = new Date('2026-10-12T00:00:00Z');
const bounds = {west:140,east:150,south:-10,north:0};
const event = (id, latitude, longitude, observed_at, sources=['VIIRS_NOAA20_NRT']) =>
  ({event_id:id,latitude,longitude,observed_at,sources});

test('area summary counts observations and repeated cells without calling them fires', () => {
  const snapshot = {events:[
    event('a',-6.025,145.025,'2026-10-11T23:00:00Z'),
    event('b',-6.025,145.025,'2026-10-11T20:00:00Z'),
    event('c',-7.025,146.025,'2026-10-11T08:00:00Z'),
    event('outside',-6.025,151.025,'2026-10-11T23:00:00Z'),
    event('expired',-7.025,146.025,'2026-10-10T23:00:00Z')],sources:[]};
  const result = summarizeArea(snapshot,bounds,24,now);
  assert.deepEqual(result,{candidateCount:3,locationCount:2,repeatedLocationCount:1,
    latestObservedAt:'2026-10-11T23:00:00Z',recentCount:2,earlierCount:1,
    comparisonHours:12,sourceProblems:[]});
});

test('area summary respects source selection, antimeridian bounds, and failed sources', () => {
  const snapshot = {events:[
    event('a',-5,179,'2026-10-11T23:00:00Z',['VIIRS_NOAA20_NRT']),
    event('b',-5,-179,'2026-10-11T22:00:00Z',['VIIRS_NOAA21_NRT']),
    event('c',-5,0,'2026-10-11T23:00:00Z')],
    sources:[{key:'VIIRS_NOAA20_NRT',status:'failed'},
      {key:'VIIRS_NOAA21_NRT',status:'complete'}]};
  const result = summarizeArea(snapshot,{west:170,east:-170,south:-10,north:0},6,now,
    'VIIRS_NOAA21_NRT');
  assert.equal(result.candidateCount,1);
  assert.equal(result.comparisonHours,3);
  assert.deepEqual(result.sourceProblems,['VIIRS_NOAA20_NRT']);
});

test('empty area has no last observation or implied activity', () => {
  const result = summarizeArea({events:[],sources:[]},bounds,72,now);
  assert.equal(result.candidateCount,0);
  assert.equal(result.latestObservedAt,null);
  assert.equal(result.repeatedLocationCount,0);
});

test('agency source failures do not imply satellite gaps in the area summary', () => {
  const result = summarizeArea({events:[],sources:[
    {key:'nifc_wfigs',status:'failed'},
    {key:'VIIRS_NOAA20_NRT',status:'complete'}]},bounds,24,now);
  assert.deepEqual(result.sourceProblems,[]);
});
