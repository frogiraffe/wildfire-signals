// WGS84 research grid renderer. Grid rectangles are archived candidate bins, never fire perimeters.
export function spatialGridCells(region) {
  if (!Array.isArray(region?.published_bins)) throw new Error('Missing published spatial bins');
  return region.published_bins.map(bin=>{
    const v=bin.bounds_wgs84;
    if (!Array.isArray(v)||v.length!==4||v.some(n=>!Number.isFinite(n))||
        v[0]>=v[2]||v[1]>=v[3]||v[0]<-90||v[2]>90||v[1]<-180||v[3]>180||
        !Number.isSafeInteger(bin.raw_pixels)||bin.raw_pixels<0) throw new Error('Invalid grid cell');
    return {id:bin.bin_id,south:v[0],west:v[1],north:v[2],east:v[3],
      pixels:bin.raw_pixels,providers:bin.provider_counts??{},classification:bin.classification,dates:bin.distinct_dates};
  });
}
export function renderSpatialGrid(root,region,filter='all',onSelect=null,provider='all'){
  if (!['all','VIIRS_NOAA20_STANDARD','VIIRS_SNPP_STANDARD'].includes(provider)) throw new Error('Unknown satellite sensor');
  const cells=spatialGridCells(region).filter(c=>(filter==='all'||c.classification===filter) &&
    (provider==='all'||(c.providers[provider]??0)>0));
  root.replaceChildren();
  if(!cells.length){const p=document.createElement('p');p.textContent='No published bins match this filter. Unpublished bins are not mapped.';root.append(p);return;}
  const ns='http://www.w3.org/2000/svg';
  const svg=document.createElementNS(ns,'svg');
  svg.setAttribute('viewBox','0 0 760 420');svg.setAttribute('role','img');
  svg.setAttribute('aria-label','Published 0.01 degree archived thermal observation cells, not wildfire perimeters');
  const minLon=Math.min(...cells.map(c=>c.west)),maxLon=Math.max(...cells.map(c=>c.east));
  const minLat=Math.min(...cells.map(c=>c.south)),maxLat=Math.max(...cells.map(c=>c.north));
  const lonScale=680/Math.max(.01,maxLon-minLon),latScale=340/Math.max(.01,maxLat-minLat);
  const scale=Math.min(lonScale,latScale);
  const draw=(tag,attrs,titleText)=>{
    const node=document.createElementNS(ns,tag);
    for(const [k,v] of Object.entries(attrs))node.setAttribute(k,String(v));
    if(titleText){const t=document.createElementNS(ns,'title');t.textContent=titleText;node.append(t);}
    svg.append(node);
    return node;
  };
  const count=c=>provider==='all'?c.pixels:(c.providers[provider]??0);
  const max=Math.max(1,...cells.map(count));
  for(const c of cells){
    const x=40+(c.west-minLon)*scale,y=25+(maxLat-c.north)*scale;
    const fill=c.classification==='potential_static_thermal_source'?'#db9bc7':
      c.classification==='recurrently_observed_candidate'?'#e9b578':'#78c6bd';
    const rect=draw('rect',{x,y,width:Math.max(1,(c.east-c.west)*scale),
      height:Math.max(1,(c.north-c.south)*scale),fill,stroke:'#14232b',
      'stroke-width':.6,opacity:.25+.75*Math.sqrt(count(c)/max)},
      c.id+'; '+count(c)+' selected-sensor pixels; '+c.dates+' observed dates; '+c.classification);
    if (onSelect) {
      rect.setAttribute('tabindex','0');rect.setAttribute('role','button');
      rect.setAttribute('aria-label','Inspect archived cell '+c.id);
      rect.classList.add('inspectable-grid-cell');
      rect.addEventListener('click',()=>onSelect(c.id));
      rect.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(c.id);}});
    }
  }
  root.append(svg);
}
