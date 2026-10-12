import test from 'node:test';
import assert from 'node:assert/strict';
import {recordAnalysis} from '../../public/analysis-answers.mjs';

const now = new Date('2026-10-12T12:00:00Z');
const manifest = {last_scan_at:'2026-10-12T11:45:00Z',data_status:'fresh'};

test('agency evidence answers presence without claiming current fire behavior', () => {
  const result = recordAnalysis({provider:'cwfis',agency_status:'OC',
    modified_at:'2026-10-12T10:00:00Z'},'incident',manifest,
    [{key:'cwfis',status:'complete'}],now);
  assert.equal(result.presence,'agency_out_of_control');
  assert.equal(result.quality,'current_snapshot');
  assert.equal(result.sourceTime,'2026-10-12T10:00:00Z');
  assert.equal(result.ignition,'unavailable');
  assert.equal(result.spread,'unavailable');
  assert.equal(result.ending,'unavailable');
  assert.equal(result.spreadReason,'spread_missing_inputs');
});

test('under control remains a source status, never a fire extinction claim', () => {
  const result = recordAnalysis({provider:'cwfis',agency_status:'UC',
    modified_at:'2026-10-12T09:00:00Z'},'incident',manifest,[],now);
  assert.equal(result.presence,'agency_under_control');
  assert.equal(result.ending,'unavailable');
});

test('candidate stays unconfirmed and does not get a spread answer', () => {
  const result = recordAnalysis({observed_at:'2026-10-12T11:00:00Z',
    sources:['VIIRS_NOAA20_NRT']},'candidate',manifest,[],now);
  assert.equal(result.presence,'satellite_unconfirmed');
  assert.equal(result.spreadReason,'spread_needs_confirmed_fire');
  assert.equal(result.endingReason,'ending_needs_confirmed_fire');
});

test('source failure and stale snapshot remain visible in the answer', () => {
  const agency = {provider:'nifc_wfigs',modified_at:'2026-10-12T09:00:00Z'};
  assert.equal(recordAnalysis(agency,'incident',manifest,
    [{key:'nifc_wfigs',status:'failed'}],now).quality,'source_unavailable');
  assert.equal(recordAnalysis(agency,'incident',{
    ...manifest,last_scan_at:'2026-10-12T08:00:00Z'},
    [{key:'nifc_wfigs',status:'complete'}],now).quality,'snapshot_stale');
  assert.equal(recordAnalysis(agency,'incident',{
    ...manifest,data_status:'partial'},
    [{key:'nifc_wfigs',status:'complete'}],now).quality,'other_sources_partial');
});
