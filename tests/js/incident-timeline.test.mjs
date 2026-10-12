import assert from 'node:assert/strict';
import test from 'node:test';
import {incidentTimeline} from '../../public/incident-timeline.mjs';

test('agency timeline reports only observed source record changes in order', () => {
  const incident = {provider:'cwfis',official_id:'CA-1'};
  const snapshot = {manifest:{last_scan_at:'2026-10-12T14:00:00Z'},details:{incident_history:{
    'cwfis:CA-1':[
      {change:'record_changed',seen_at:'2026-10-12T14:00:00Z',agency_status:'BH'},
      {change:'first_seen',seen_at:'2026-10-12T12:00:00Z',agency_status:'UC'},
      {change:'record_changed',seen_at:'2026-10-12T15:00:00Z',agency_status:'OC'}]}}};
  assert.deepEqual(incidentTimeline(snapshot,incident).map(x=>x.agency_status),['UC','BH']);
});

test('missing history stays unknown rather than implying a fire ended', () => {
  assert.deepEqual(incidentTimeline({manifest:{},details:{}},
    {provider:'nifc_wfigs',official_id:'US-1'}),[]);
});
