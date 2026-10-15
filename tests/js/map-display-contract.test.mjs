import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const html = readFileSync('public/index.html','utf8');
const js = readFileSync('public/main.mjs','utf8');

test('map visualization provides two explicit observation views', () => {
  assert.match(html, /id="candidate-display"/);
  assert.match(html, /value="points"/);
  assert.match(html, /value="density"/);
  assert.match(html, /not fire risk/);
});
test('density source remains independent of clustered points', () => {
  assert.match(js, /addSource\('candidate-density'/);
  assert.match(js, /type:'heatmap',source:'candidate-density'/);
  assert.match(js, /getSource\('candidate-density'\)\.setData/);
});
test('display selection toggles heatmap and marker layer', () => {
  assert.match(js, /setLayoutProperty\('candidate-density','visibility'/);
  assert.match(js, /setLayoutProperty\('candidates','visibility'/);
});

test('legend distinguishes source and polygon evidence without risk claims', () => {
  assert.match(html, /class="map-legend"/);
  assert.match(html, /Satellite thermal candidates/);
  assert.match(html, /Agency-reported incidents/);
  assert.match(html, /Official fire perimeter when available/);
  assert.match(html, /not the area burning or danger level/);
});

test('agency incident geometry is visually distinct from satellite markers', () => {
  assert.match(js, /map\.addImage\('agency-diamond'/);
  assert.match(js, /id:source,type:'symbol',source/);
  assert.match(js, /'icon-image':'agency-diamond'/);
  assert.match(js, /id:source,type:'circle',source/);
});

test('source and official perimeter visibility can be changed independently', () => {
  assert.match(html, /id="show-agency"/);
  assert.match(html, /id="show-perimeters"/);
  assert.match(js, /\['incidents',el\('show-agency'\)\.checked\]/);
  assert.match(js, /\['nifc-perimeter-fill',el\('show-perimeters'\)\.checked\]/);
  assert.match(js, /\['nifc-perimeter-line',el\('show-perimeters'\)\.checked\]/);
});
