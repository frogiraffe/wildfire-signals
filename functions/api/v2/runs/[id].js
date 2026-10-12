import {json} from '../../../../worker/snapshot-data.js';

export async function onRequestGet() {
  return json({error:'forecast_run_unavailable',reason:'No validated forecast archive is published'},404);
}
