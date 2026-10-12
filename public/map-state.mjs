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
    failures:'failures', close:'Close details', ambiguous:'Multiple nearby agency records — ambiguous association.',
    areaTitle:'Visible map area', areaScope:'Counts use the map viewport, not a country boundary.',
    areaCandidates:'Candidate cell-hours', areaLocations:'Observed cells',
    areaRepeated:'Cells seen in 2+ hours', areaLatest:'Latest observation',
    areaCompare:'Recent / preceding', areaHours:'hours',
    areaQuality:'Incomplete source data', areaUnavailable:'No verified snapshot is available.',
    areaCaveat:'Thermal candidates only. Counts do not measure fire size or spread.',
    leadTitle:'Places to inspect',leadScope:'Cells observed within the last 12 hours in this map view (or the shorter selected window). Ordered for review, not by danger.',
    leadEmpty:'No matching recent observations in the available data. This does not mean no fire.',
    leadRepeated:'Observed in {hours} distinct hours',leadSingle:'Observed in one hour',
    leadStale:'Snapshot is stale; recent observations may be missing.',
    leadPartial:'Some sources failed; check the source states below.',
    leadSatellitePartial:'Some satellite sources failed; this list may be incomplete.',
    leadUnknown:'No verified snapshot is available.',
    timelineTitle:'Agency record change history',
    timelineScope:'First observation here and up to four latest source record changes. This is not a history of fire spread.',
    timelineEmpty:'No record changes are retained for this incident.',
    timelineFirst:'First seen here',timelineChanged:'Source record changed',
    timelineSourceDate:'Source update',agencyStatus:'Agency status',
    analysisTitle:'What the evidence can answer',
    analysisScope:'Four analysis questions for this selected record. Unknown means the required evidence or validated model is unavailable.',
    analysisEvidence:'Data state',analysisSourceTime:'Source time',
    analysisWhere:'Where is a fire now?',analysisIgnition:'Could a fire start here?',
    analysisSpread:'Where could it spread?',analysisEnding:'Will it remain active or end?',
    satellite_unconfirmed:'Satellite thermal candidate; a wildfire is not confirmed.',
    agency_out_of_control:'Agency record reports out of control.',
    agency_being_held:'Agency record reports being held.',
    agency_under_control:'Agency record reports under control; this does not mean extinguished.',
    agency_reported:'Agency wildfire record exists; current burning state is unverified.',
    current_snapshot:'Current collection snapshot',snapshot_stale:'Collection snapshot is stale',
    other_sources_partial:'Some sources are incomplete',source_unavailable:'This source failed or was deferred',
    snapshot_unavailable:'Collection state unavailable',source_unknown:'Source state unavailable',
    unavailable:'No validated probability available.',
    ignition_unvalidated:'No regional ignition labels, coverage audit, or calibrated model.',
    spread_missing_inputs:'No verified evolving perimeter, fuel, terrain, intervention data, and evaluated spread model.',
    spread_needs_confirmed_fire:'This thermal candidate is not a verified wildfire with a starting perimeter.',
    ending_missing_outcomes:'No comparable timed control/extinguishment outcomes or evaluated model.',
    ending_needs_confirmed_fire:'A wildfire and its outcome are not independently established.',
    weatherTitle:'Weather at the recorded location',
    weatherScope:'NWS grid forecast for this US location. It is not an observation at the fire or a spread prediction.',
    weatherLoading:'Loading NWS forecast…',weatherUnavailable:'NWS forecast unavailable for this location or request. Weather effect is unknown.',
    weatherStale:'The source forecast is over 12 hours old.',
    weatherUpdated:'Source updated',weatherReceived:'Retrieved',weatherHour:'In {hours} h',
    weatherWind:'Wind',weatherGust:'Gust',weatherTemp:'Temperature',
    weatherHumidity:'Humidity',weatherRain:'Forecast rain',weatherFrom:'from',
    weatherMissing:'—',weatherRainWindow:'forecast interval',
    weatherIntervals:'Source validity intervals',
    weatherChangeTitle:'Forecast changes',
    weatherChangeScope:'Change from the current forecast at this NWS grid point. Positive direction turn means clockwise.',
    weatherTurn:'Wind direction turn',
    weatherChangeCaveat:'These are changes in forecast conditions, not measured effects on this fire or a spread probability.',
    weatherFootnote:'Rain is the amount for its stated interval, not a measured total. This forecast is not saved to the historical training archive.',
    statusOC:'Out of control',statusBH:'Being held',statusUC:'Under control'},
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
    failures:'hata', close:'Ayrıntıları kapat', ambiguous:'Birden çok yakın kurum kaydı — belirsiz ilişki.',
    areaTitle:'Görünen harita alanı', areaScope:'Sayılar ülke sınırına değil, ekranda görünen alana aittir.',
    areaCandidates:'Aday hücre-saat', areaLocations:'Gözlenen hücre',
    areaRepeated:'2+ saatte görülen hücre', areaLatest:'Son gözlem',
    areaCompare:'Son / önceki', areaHours:'saat',
    areaQuality:'Eksik kaynak verisi', areaUnavailable:'Doğrulanmış veri görüntüsü yok.',
    areaCaveat:'Bunlar termal adaylardır; sayılar yangın alanı veya yayılma ölçümü değildir.',
    leadTitle:'İncelenecek konumlar',leadScope:'Bu harita görünümünde son 12 saatte gözlenen hücreler (seçilen aralık daha kısaysa o aralık). Sıralama tehlike derecesi değildir.',
    leadEmpty:'Mevcut veride eşleşen yakın zamanlı gözlem yok. Bu, yangın olmadığı anlamına gelmez.',
    leadRepeated:'{hours} ayrı saatte gözlendi',leadSingle:'Tek saatte gözlendi',
    leadStale:'Veri görüntüsü eski; yakın zamanlı gözlemler eksik olabilir.',
    leadPartial:'Bazı kaynaklar başarısız; aşağıdaki kaynak durumlarını kontrol edin.',
    leadSatellitePartial:'Bazı uydu kaynakları başarısız; liste eksik olabilir.',
    leadUnknown:'Doğrulanmış veri görüntüsü yok.',
    timelineTitle:'Kurum kaydı değişim geçmişi',
    timelineScope:'Burada ilk gözlem ve en fazla dört son kaynak kaydı değişikliği. Yangının yayılma geçmişi değildir.',
    timelineEmpty:'Bu olay için saklanan kayıt değişimi yok.',
    timelineFirst:'Burada ilk görüldü',timelineChanged:'Kaynak kaydı değişti',
    timelineSourceDate:'Kaynak güncellemesi',agencyStatus:'Kurum durumu',
    analysisTitle:'Kanıtın yanıtlayabildikleri',
    analysisScope:'Seçilen kayıt için dört analiz sorusu. Bilinmiyor, gerekli kanıtın veya doğrulanmış modelin bulunmadığı anlamına gelir.',
    analysisEvidence:'Veri durumu',analysisSourceTime:'Kaynak zamanı',
    analysisWhere:'Şu anda nerede yangın var?',analysisIgnition:'Burada yangın çıkabilir mi?',
    analysisSpread:'Nereye ilerleyebilir?',analysisEnding:'Etkin kalır mı, söner mi?',
    satellite_unconfirmed:'Uydu termal adayı; orman/arazi yangını doğrulanmadı.',
    agency_out_of_control:'Kurum kaydı kontrol dışı olarak bildiriyor.',
    agency_being_held:'Kurum kaydı sınırları içinde tutuluyor olarak bildiriyor.',
    agency_under_control:'Kurum kaydı kontrol altında olarak bildiriyor; bu, söndüğü anlamına gelmez.',
    agency_reported:'Kurumun yangın kaydı var; şu an yanma durumu doğrulanmadı.',
    current_snapshot:'Güncel toplama görüntüsü',snapshot_stale:'Toplama görüntüsü eski',
    other_sources_partial:'Bazı kaynaklar eksik',source_unavailable:'Bu kaynak başarısız veya ertelendi',
    snapshot_unavailable:'Toplama durumu bilinmiyor',source_unknown:'Kaynak durumu bilinmiyor',
    unavailable:'Doğrulanmış olasılık yok.',
    ignition_unvalidated:'Bölgesel tutuşma etiketleri, kapsam denetimi ve kalibre model yok.',
    spread_missing_inputs:'Doğrulanmış değişen çevre, yakıt, arazi, müdahale verisi ve sınanmış yayılım modeli yok.',
    spread_needs_confirmed_fire:'Bu termal aday, başlangıç çevresi olan doğrulanmış yangın değil.',
    ending_missing_outcomes:'Karşılaştırılabilir zamanlı kontrol/sönme sonuçları ve sınanmış model yok.',
    ending_needs_confirmed_fire:'Yangın ve sonucu bağımsız olarak doğrulanmadı.',
    weatherTitle:'Kayıt konumundaki hava',
    weatherScope:'Bu ABD konumu için NWS grid tahmini. Yangın yerindeki ölçüm veya yayılım tahmini değildir.',
    weatherLoading:'NWS tahmini yükleniyor…',weatherUnavailable:'Bu konumda NWS tahmini veya istek kullanılamıyor. Havanın etkisi bilinmiyor.',
    weatherStale:'Kaynak tahmini 12 saatten eski.',
    weatherUpdated:'Kaynak güncellemesi',weatherReceived:'Alınma',weatherHour:'{hours} saat sonra',
    weatherWind:'Rüzgâr',weatherGust:'Hamle',weatherTemp:'Sıcaklık',
    weatherHumidity:'Nem',weatherRain:'Tahmini yağış',weatherFrom:'geldiği yön',
    weatherMissing:'—',weatherRainWindow:'tahmin aralığı',
    weatherIntervals:'Kaynak geçerlilik aralıkları',
    weatherChangeTitle:'Tahmini hava değişimi',
    weatherChangeScope:'Bu NWS grid noktasındaki mevcut tahmine göre fark. Pozitif yön dönüşü saat yönündedir.',
    weatherTurn:'Rüzgâr yönü dönüşü',
    weatherChangeCaveat:'Bunlar tahmini hava koşullarındaki farklardır; yangına ölçülmüş etkisi veya yayılma olasılığı değildir.',
    weatherFootnote:'Yağış belirtilen aralığın miktarıdır; ölçülen toplam değildir. Bu tahmin tarihsel eğitim arşivine kaydedilmez.',
    statusOC:'Kontrol dışı',statusBH:'Sınırları içinde tutuluyor',statusUC:'Kontrol altında'}
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
