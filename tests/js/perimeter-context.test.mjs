import test from 'node:test';
import assert from 'node:assert/strict';
import {fetchNifcPerimeter, parseNifcPerimeter} from '../../public/perimeter-context.mjs';

const ID = '{548A8D28-1A04-48EE-9011-ABA023175D43}';
const NOW = new Date('2026-10-12T12:00:00Z');
const ring = [[-120,40],[-119,40],[-119,41],[-120,41],[-120,40]];
const feature = (date, geometry = {type:'Polygon',coordinates:[ring]}) => ({
  type:'Feature',properties:{poly_IRWINID:ID,poly_PolygonDateTime:Date.parse(date),
    attr_IncidentTypeCategory:'WF',poly_IncidentName:'Example'},geometry,
});

test('uses only the latest exact-ID wildfire perimeter and keeps its source time', () => {
  const result = parseNifcPerimeter({type:'FeatureCollection',features:[
    feature('2026-10-10T00:00:00Z'),feature('2026-10-12T06:00:00Z')]},ID,NOW);
  assert.equal(result.status,'mapped');
  assert.equal(result.observedAt,'2026-10-12T06:00:00.000Z');
  assert.equal(result.stale,false);
  assert.equal(result.geojson.features.length,1);
  assert.deepEqual(result.geojson.features[0].geometry.coordinates,[ring]);
});

test('empty exact-ID result is unavailable, never an empty fire or spread area', () => {
  const result = parseNifcPerimeter({type:'FeatureCollection',features:[]},ID,NOW);
  assert.equal(result.status,'not_listed');
  assert.equal(result.geojson.features.length,0);
});

test('rejects wrong ID, non-wildfire, future time, and invalid geometry', () => {
  const bad = [
    {...feature('2026-10-12T06:00:00Z'),properties:{...feature('2026-10-12T06:00:00Z').properties,
      poly_IRWINID:'{11111111-1111-1111-1111-111111111111}'}},
    {...feature('2026-10-12T06:00:00Z'),properties:{...feature('2026-10-12T06:00:00Z').properties,
      attr_IncidentTypeCategory:'RX'}},
    feature('2026-10-13T06:00:00Z'),
    feature('2026-10-12T06:00:00Z',{type:'Polygon',coordinates:[[[999,40],[-119,40],[-119,41],[999,40]]]})];
  for (const row of bad) assert.throws(() => parseNifcPerimeter(
    {type:'FeatureCollection',features:[row]},ID,NOW));
  assert.throws(() => parseNifcPerimeter({type:'FeatureCollection',features:[],
    exceededTransferLimit:true},ID,NOW));
});

test('fetches one bounded official query and flags an old perimeter', async () => {
  let requested;
  const result = await fetchNifcPerimeter(ID,{now:() => NOW,
    fetchImpl:async (url,options) => {
      requested = new URL(url);
      assert.equal(options.headers.Accept,'application/geo+json');
      return {ok:true,text:async () => JSON.stringify({type:'FeatureCollection',
        features:[feature('2026-10-01T00:00:00Z')]})};
    }});
  assert.equal(requested.hostname,'services3.arcgis.com');
  assert.match(requested.pathname,/WFIGS_Interagency_Perimeters_Current/);
  assert.equal(requested.searchParams.get('where'),
    `poly_IRWINID='${ID}' AND attr_IncidentTypeCategory='WF'`);
  assert.equal(requested.searchParams.get('resultRecordCount'),'10');
  assert.equal(result.stale,true);
  assert.equal(result.receivedAt,NOW.toISOString());
  assert.equal(result.sourceUrl,requested.toString());
  await assert.rejects(() => fetchNifcPerimeter("' OR 1=1",{fetchImpl:async () => {
    throw Error('must not request');
  }}),/invalid/);
});
