import {readSnapshot,json,unavailable} from '../../../worker/snapshot-data.js';

export async function onRequestGet({env}) {
  let snapshot;
  try { snapshot = await readSnapshot(env); } catch { return unavailable(); }
  return json({schema_version:2,generated_at:snapshot.manifest.generated_at,
    data_status:snapshot.manifest.data_status,sources:snapshot.sources});
}
