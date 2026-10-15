// Temporal archive visualization: descriptive detections, never wildfire rates.
export const timelineMetrics={
  raw_pixels:'Archived thermal pixels',
  candidate_cell_hours:'Candidate cell-hours'
};
export function historicalTimeline(studies,{from,to,provider,metric='raw_pixels'}) {
  if (!Object.hasOwn(timelineMetrics,metric) || !/^\d{4}-(0[1-9]|1[0-2])$/.test(from) ||
      !/^\d{4}-(0[1-9]|1[0-2])$/.test(to) || from>to)
    throw new Error('Invalid historical timeline selection');
  const series=studies.map(({pilot,report})=>{
    if (from<report.start_date.slice(0,7) || to>report.end_date.slice(0,7))
      throw new Error('Selection outside archive period');
    const permitted=new Set(report.source_asset_manifest.map(x=>x.provider));
    if(provider!=='all' && !permitted.has(provider))
      throw new Error('Sensor unavailable in selected study');
    const grouped=new Map();
    for(const row of report.monthly_rows) {
      if(row.observed_month<from || row.observed_month>to ||
         (provider!=='all' && row.provider!==provider))continue;
      if(!Number.isSafeInteger(row[metric]) || row[metric]<0)
        throw new Error('Malformed historical observation counts');
      grouped.set(row.observed_month,(grouped.get(row.observed_month)||0)+row[metric]);
    }
    return {id:pilot.id,label:pilot.label,sha256:report.evidence_sha256,months:grouped};
  });
  const months=[...new Set(series.flatMap(s=>[...s.months.keys()]))].sort();
  const points=months.map(month=>({month,values:series.map(s=>s.months.get(month)??null)}));
  return {metric,provider,from,to,series:series.map(({id,label,sha256})=>({id,label,sha256})),
    points,observationOpportunityVerified:false,fireRiskInferenceSupported:false,
    note:'Missing archive rows are unknown exposure, not zero fire. Values are satellite thermal observations and not cross-region comparable fire incidence.'};
}

export function renderHistoricalTimeline(root,data) {
  root.replaceChildren();
  if(!data.points.length){
    const p=document.createElement('p');p.textContent='No archived candidate months in this selection; satellite opportunity is unknown.';
    root.append(p);return;
  }
  const ns='http://www.w3.org/2000/svg';
  const svg=document.createElementNS(ns,'svg');
  svg.setAttribute('viewBox','0 0 760 260');svg.setAttribute('role','img');
  svg.setAttribute('aria-label',data.series.map(s=>s.label).join(' vs ')+
    ': historical '+data.metric.replaceAll('_',' ')+' by archived UTC month; no verified satellite exposure');
  const add=(tag,attrs,text)=>{const e=document.createElementNS(ns,tag);
    for(const [key,val] of Object.entries(attrs))e.setAttribute(key,String(val));
    if(text!==undefined)e.textContent=String(text);
    svg.append(e);return e;};
  const values=data.points.flatMap(p=>p.values).filter(Number.isFinite);
  const max=Math.max(1,...values);
  const x=i=>64+(i/Math.max(1,data.points.length-1))*664;
  const y=v=>218-(v/max)*175;
  for(let i=0;i<=4;i++){
    const value=Math.round(max*i/4),yy=y(max*i/4);
    add('line',{x1:64,x2:728,y1:yy,y2:yy,stroke:'#42616d','stroke-width':1});
    add('text',{x:56,y:yy+4,fill:'#c4d5d8','font-size':11,'text-anchor':'end'},value);
  }
  const colors=['#79cbc2','#eab27a','#a5aff1','#dd8dba'];
  data.series.forEach((series,si)=>{
    let segment=[];
    const flush=()=>{if(segment.length){
      add('polyline',{points:segment.join(' '),fill:'none',stroke:colors[si%colors.length],
        'stroke-width':2.5,'stroke-linejoin':'round'});segment=[];}};
    data.points.forEach((point,i)=>{
      const v=point.values[si];
      if(v===null){flush();return;}
      segment.push(x(i)+','+y(v));
      const dot=add('circle',{cx:x(i),cy:y(v),r:3.5,fill:colors[si%colors.length]});
      const title=document.createElementNS(ns,'title');
      title.textContent=series.label+' · '+point.month+': '+v+' archived '+data.metric.replaceAll('_',' ');
      dot.append(title);
    });flush();
    add('rect',{x:68+si*175,y:238,width:11,height:11,fill:colors[si%colors.length]});
    add('text',{x:84+si*175,y:248,fill:'#dbe9ea','font-size':12},series.label);
  });
  for(let i=0;i<data.points.length;i+=Math.max(1,Math.ceil(data.points.length/9)))
    add('text',{x:x(i),y:231,fill:'#c4d5d8','font-size':10,'text-anchor':'middle'},data.points[i].month);
  root.append(svg);
}
