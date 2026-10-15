import test from 'node:test';
import assert from 'node:assert/strict';
import {observationSlice} from '../../public/observation-slice.mjs';
const now=new Date('2026-10-15T12:00:00Z');
const events=[
  {observed_at:'2026-10-15T06:00:00Z'},
  {observed_at:'2026-10-15T08:00:00Z'},
  {observed_at:'2026-10-15T10:00:00Z'},
  {observed_at:'2026-10-15T12:00:00Z'},
  {observed_at:'invalid'}
];
test('three time slices are disjoint and honor endpoints',()=>{
  const slices=[0,1,2].map(i=>observationSlice(events,6,String(i),now));
  assert.deepEqual(slices.map(v=>v.length),[1,1,2]);
  assert.equal(new Set(slices.flat()).size,4);
});
test('full window retains original input, invalid slice defaults to full',()=>{
  assert.strictEqual(observationSlice(events,6,'all',now),events);
  assert.strictEqual(observationSlice(events,6,'invalid',now),events);
});
