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
