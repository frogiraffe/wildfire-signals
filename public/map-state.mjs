export const MESSAGES = {
  en: {title:'Wildfire Signals', candidates:'Satellite candidates', incidents:'Agency incidents',
    timeScope:'Time window filters satellite observations. Agency records show the current source layer; check each agency update date.',
    all:'All sources', time:'Time window', source:'Source', status:'Status',
    fresh:'Updated', stale:'Data is stale. Missing observations are possible.',
    unknown:'No verified scan is available yet.', partial:'Some sources failed; records may be missing.', empty:'No records in this view.',
    provisional:'Nearby agency record — provisional association',
    candidate:'Satellite candidate; fire is not independently confirmed.',
    agency:'Agency incident record', updated:'Last scan', health:'Source health',
    about:'Thermal detections are candidates, not confirmed fires.',
    link:'Share view', language:'Language', sourceCaveat:'Coverage and update times vary by source.',
    allKinds:'All', id:'ID', observed:'Observed', received:'Received', sources:'Sources',
    location:'Location', thermal:'Thermal trend', detections:'Detection count', provider:'Provider',
    kind:'Kind', modified:'Updated', aggregation:'Grouping', product:'Product age',
    failures:'failures', close:'Close details', ambiguous:'Multiple nearby agency records — ambiguous association.'},
  tr: {title:'Yangın Sinyalleri', candidates:'Uydu adayları', incidents:'Kurum olayları',
    timeScope:'Zaman aralığı uydu gözlemlerini süzer. Kurum kayıtları güncel kaynak katmanından gelir; her kaydın kurum güncelleme tarihini kontrol edin.',
    all:'Tüm kaynaklar', time:'Zaman aralığı', source:'Kaynak', status:'Durum',
    fresh:'Güncel', stale:'Veri eski. Eksik gözlem aralıkları olabilir.',
    unknown:'Henüz doğrulanmış tarama yok.', partial:'Bazı kaynaklar başarısız; kayıtlar eksik olabilir.', empty:'Bu görünümde kayıt yok.',
    provisional:'Yakındaki kurum kaydı — geçici ilişki',
    candidate:'Uydu adayı; bağımsız yangın doğrulaması değildir.',
    agency:'Kurum olay kaydı', updated:'Son tarama', health:'Kaynak durumu',
    about:'Termal tespitler adaydır; doğrulanmış yangın değildir.',
    link:'Görünümü paylaş', language:'Dil', sourceCaveat:'Kapsam ve güncelleme zamanı kaynağa göre değişir.',
    allKinds:'Tümü', id:'Kimlik', observed:'Gözlem', received:'Alınma', sources:'Kaynaklar',
    location:'Konum', thermal:'Termal eğilim', detections:'Tespit sayısı', provider:'Kurum',
    kind:'Tür', modified:'Güncelleme', aggregation:'Gruplama', product:'Ürün yaşı',
    failures:'hata', close:'Ayrıntıları kapat', ambiguous:'Birden çok yakın kurum kaydı — belirsiz ilişki.'}
};

export function parseState(hash = '') {
  const params = new URLSearchParams(hash.replace(/^#/, ''));
  const numeric = (key, fallback, min, max) => {
    const value = Number(params.get(key));
    return Number.isFinite(value) && params.has(key) ? Math.min(max, Math.max(min, value)) : fallback;
  };
  return {lang: params.get('lang') === 'tr' ? 'tr' : 'en',
    hours: [6, 24, 72].includes(Number(params.get('hours'))) ? Number(params.get('hours')) : 24,
    source: params.get('source') || 'all',
    kind: ['all', 'candidate', 'incident'].includes(params.get('kind')) ? params.get('kind') : 'all',
    lat: numeric('lat', 15, -85, 85), lon: numeric('lon', -60, -180, 180),
    zoom: numeric('zoom', 3, 1, 18)};
}

export function stateHash(state) {
  const params = new URLSearchParams();
  for (const key of ['lang', 'hours', 'source', 'kind', 'lat', 'lon', 'zoom']) params.set(key, String(state[key]));
  return `#${params}`;
}

export function visible(snapshot, state, now = new Date()) {
  const cutoff = now.getTime() - state.hours * 3600_000;
  const events = (snapshot.events || []).filter(item =>
    Date.parse(item.observed_at) >= cutoff &&
    (state.source === 'all' || (item.sources || []).includes(state.source)) &&
    state.kind !== 'incident');
  const incidents = (snapshot.incidents || []).filter(item =>
    (state.source === 'all' || item.provider === state.source) &&
    state.kind !== 'candidate');
  return {events, incidents};
}

export function effectiveStatus(manifest, now = new Date()) {
  if (!manifest?.last_scan_at || !Number.isFinite(Date.parse(manifest.last_scan_at))) return 'unknown';
  if (now.getTime() - Date.parse(manifest.last_scan_at) > 90 * 60_000) return 'stale';
  return manifest.data_status || 'unknown';
}

export function featureCollection(items, kind) {
  return {type:'FeatureCollection', features:items.map(item => ({type:'Feature',
    geometry:{type:'Point', coordinates:[item.longitude, item.latitude]},
    properties:{id:kind === 'candidate' ? item.event_id : `${item.provider}:${item.official_id}`,
      kind}}))};
}
