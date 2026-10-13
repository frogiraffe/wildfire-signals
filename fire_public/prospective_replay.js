/* Private source-receipt time machine; no network, no storage, no imported script. */
(function (root) {
  'use strict';
  const STATUS = 'source_bound_prospective_agency_timeline_not_fire_outcome';
  const STATES = Object.freeze(['listed','not_listed_in_complete_scan','source_unavailable']);
  const MAX_BYTES = 3*1024*1024;

  function assertBook(book) {
    if (!book || book.schema_version !== 1 || book.research_status !== STATUS ||
        book.verified_cross_provider_event_links !== 0 ||
        book.verified_nonfire_labels !== 0 ||
        book.verified_extinguishment_labels !== 0 ||
        book.forecast_skill_measured !== false ||
        !Array.isArray(book.scans) || !Array.isArray(book.cases) ||
        book.cases.length > 250 || book.agency_scan_count > 400 ||
        JSON.stringify(book).length > MAX_BYTES*2) {
      throw new Error('Source-bound unverified agency replay required.');
    }
    const seen = new Set();
    for (const row of book.cases) {
      if (!row || !['cwfis','nifc_wfigs'].includes(row.provider) ||
          typeof row.official_id !== 'string' ||
          seen.has(JSON.stringify([row.provider,row.official_id])) ||
          !Array.isArray(row.timeline) ||
          row.physical_fire_identity_verified !== false ||
          row.verified_extinguishment_at !== null || row.verified_nonfire !== false ||
          !row.timeline.some(t=>t.availability==='listed')) {
        throw new Error('Duplicate, fabricated or incomplete identity.');
      }
      seen.add(JSON.stringify([row.provider,row.official_id]));
      for (const t of row.timeline) {
        if (!STATES.includes(t.availability) ||
            t.extinguishment_label !== null ||
            t.event_identity_independently_verified !== false ||
            (t.availability==='source_unavailable'&&t.source_status==='complete') ||
            (t.availability==='listed'&&t.source_status!=='complete')) {
          throw new Error('Unsupported historical source provenance.');
        }
      }
    }
    return book;
  }

  const before = (stamp,cutoff) => Date.parse(stamp)<=Date.parse(cutoff);

  function traceAsOf(row,at) {
    const trace=row.timeline.filter(t=>before(t.captured_at,at) &&
                                      before(t.scan_at,at));
    const first=trace.find(t=>t.availability==='listed');
    const latest=trace.at(-1);
    const recent=[...trace].reverse().find(t=>t.availability==='listed');
    // First known identity must be established before it can be shown.
    if(!first)return null;
    return {
      provider:row.provider,official_id:row.official_id,
      name:recent?.source_name||row.official_id,
      firstAvailableAt:first.captured_at,
      lastListedAt:recent?.captured_at||null,
      availability:latest.availability,
      agencyStatus:latest.agency_status,
      sourceStatus:latest.source_status,
      lastScanAt:latest.scan_at,
      latestOriginalSha:recent?.observation_sha256||null,
      trace,
      verifiedFireIdentity:false, extinguishmentLabel:null, verifiedNonfire:false
    };
  }

  function stateAt(book,at,query='') {
    assertBook(book);
    if(!Number.isFinite(Date.parse(at)) ||
        Date.parse(at)>Date.parse(book.as_of))
      throw new RangeError('Requested decision time is beyond archived source visibility.');
    const term=String(query).trim().toLocaleLowerCase();
    const rows=book.cases.map(c=>traceAsOf(c,at)).filter(Boolean).filter(c=>
      !term || [c.provider,c.official_id,c.name].some(v=>
        String(v||'').toLocaleLowerCase().includes(term)));
    const state=book.scans.filter(s=>before(s.captured_at,at)&&before(s.scan_at,at));
    const lastByProvider={};
    for(const s of state)lastByProvider[s.provider]=s;
    return {at,rows,sourceStates:lastByProvider,
            verifiedWildfireCount:null,verifiedFireAbsenceCount:null};
  }

  function excerpt(book,at,sourceIdentity) {
    const state=stateAt(book,at);
    const row=state.rows.find(c=>JSON.stringify([c.provider,c.official_id])===sourceIdentity);
    if(!row)throw new Error('Selected source identity not known at this decision time.');
    return {schema_version:1,
      research_status:STATUS,decision_time:at,
      source_identity:sourceIdentity,
      source_snapshot_sha256:state.sourceStates[row.provider]?.snapshot_key||null,
      provider_state:state.sourceStates[row.provider],
      known_record:row,
      extinguishment_label:null,
      confirmed_nonfire_label:null,
      independently_verified_physical_fire_identity:false,
      no_future_receipts_included:true};
  }

  function mount(doc,book) {
    assertBook(book);
    const get=id=>doc.getElementById(id);
    const add=(tag,text)=>{
      const e=doc.createElement(tag);
      if(text!==undefined)e.textContent=String(text);
      return e;
    };
    const times=[...new Set(book.scans.map(s=>s.captured_at))].sort();
    const last=times.at(-1);
    let selected=null;
    get('asof-source').textContent='Maximum source replay time: '+book.as_of+
      ' · '+book.known_source_identities+' agency identities captured within the archive';
    for(const moment of times) {
      const option=add('option',moment+' UTC (captured)');
      option.value=moment;
      get('moment').append(option);
    }
    if(!times.length) {
      const option=add('option','No captured agency receipt yet');
      option.value=book.as_of;get('moment').append(option);
    } else get('moment').value=last;

    function render() {
      const at=get('moment').value||book.as_of;
      const all=stateAt(book,at);
      const filtered=stateAt(book,at,get('find').value);
      const list=get('event-list');list.replaceChildren();
      get('count').textContent=filtered.rows.length+' of '+all.rows.length+
        ' source identities known at this captured moment';
      if(!filtered.rows.some(x=>JSON.stringify([x.provider,x.official_id])===selected))
        selected=filtered.rows[0]?JSON.stringify([filtered.rows[0].provider,filtered.rows[0].official_id]):null;
      for(const row of filtered.rows) {
        const item=add('li');
        const button=add('button');
        button.type='button';
        const identity=JSON.stringify([row.provider,row.official_id]);
        button.setAttribute('aria-pressed',String(identity===selected));
        button.append(add('strong',row.name),
                      add('small',row.provider+': '+row.official_id),
                      add('small',row.availability+
                          (row.agencyStatus?' · source status: '+row.agencyStatus:'')));
        button.addEventListener('click',()=>{
          selected=identity;render();
          get('detail').setAttribute('tabindex','-1');
          get('detail').focus();
        });
        item.append(button);list.append(item);
      }
      const sourceState=Object.entries(all.sourceStates).map(([provider,s])=>
        provider+': '+s.status+' (received '+s.captured_at+')').join(' · ');
      get('quality').textContent=sourceState||
        'No agency source receipt was available at the selected time.';
      const detail=get('detail');detail.replaceChildren();
      const row=filtered.rows.find(x=>
        JSON.stringify([x.provider,x.official_id])===selected);
      get('download').disabled=!row;
      if(!row) {
        detail.append(add('p','No known source identity at this selected time or search.'));
        return;
      }
      detail.append(add('h2',row.name),
        add('p','Agency source ID: '+row.provider+' · '+row.official_id),
        add('p','As-of availability: '+row.availability+' · agency status: '+
            (row.agencyStatus||'not provided')),
        add('p','First actually captured: '+row.firstAvailableAt+
            ' · last listed: '+(row.lastListedAt||'never')),
        add('p','No verified fire-out time, independent same-event crosswalk or nonfire label.'));
      const summary=add('h3','Captured source timeline');
      detail.append(summary);
      const table=add('table');
      const head=add('thead');
      const tr=add('tr');
      for(const name of ['Scan UTC','Captured UTC','Provider state','Listed in source','Agency status','Source modified UTC','Original receipt SHA prefix'])
        tr.append(add('th',name));
      head.append(tr);table.append(head);
      const body=add('tbody');
      for(const entry of row.trace) {
        const line=add('tr');
        line.dataset.state=entry.availability;
        for(const value of [entry.scan_at,entry.captured_at,entry.source_status,
                            entry.availability,entry.agency_status||'—',
                            entry.source_modified_at||'—',
                            (entry.receipt_sha256||'').slice(0,20)])
          line.append(add('td',value));
        body.append(line);
      }
      table.append(body);
      const panel=add('div');panel.id='trace';panel.append(table);
      detail.append(panel);
      const warning=add('p','Source not-listed is NOT extinguished; failed/deferred is UNKNOWN. '+
        'The timeline only reports what was captured at or before the chosen decision time.');
      warning.className='warning';
      detail.append(warning);
    }

    get('moment').addEventListener('change',render);
    get('find').addEventListener('input',render);
    get('download').addEventListener('click',()=>{
      if(!selected)return;
      const item=excerpt(book,get('moment').value||book.as_of,selected);
      const content=JSON.stringify(item,null,2)+'\n';
      const url=URL.createObjectURL(new Blob([content],{type:'application/json'}));
      const link=add('a');link.href=url;link.download='agency-as-of-evidence.json';
      doc.body.append(link);link.click();link.remove();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
    });
    render();
  }

  root.AgencyReplay=Object.freeze({assertBook,stateAt,traceAsOf,excerpt,mount});
})(globalThis);
