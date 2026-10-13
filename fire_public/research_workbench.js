/* Self-contained private research browser, no network, no local storage, no external modules. */
(function (root) {
  'use strict';
  const STATES = Object.freeze([
    'not_started', 'investigating', 'blocked', 'request_external_adjudication'
  ]);
  const LIMIT_NOTE = 3000;
  const MAX_SESSION_BYTES = 250000;
  const LABELS = {
    not_started: 'Not started',
    investigating: 'Investigating',
    blocked: 'Blocked / awaiting source',
    request_external_adjudication: 'External adjudication requested (NOT verified)'
  };

  function assertBook(book) {
    if (!book || book.schema_version !== 1 ||
        book.research_status !== 'private_historical_investigation_queue_not_ground_truth' ||
        book.verified_same_event_crosswalks !== 0 ||
        book.verified_nonfire_labels !== 0 ||
        book.measured_model_skill !== false ||
        book.no_confirmed_fire_or_nonfire_labels !== true ||
        !/^[a-f0-9]{64}$/.test(book.source_casebook_sha256 || '') ||
        !Array.isArray(book.rows) ||
        book.rows.length !== book.original_candidate_population ||
        book.rows.length < 1 || book.rows.length > 400) {
      throw new Error('Unverified and source-bound original research queue required.');
    }
    const seen = new Set();
    for (const row of book.rows) {
      if (!row || typeof row.candidate_id !== 'string' ||
          seen.has(row.candidate_id) || row.same_physical_event_verified !== false ||
          row.independent_nonfire_verified !== false ||
          row.risk_or_forecast_score !== null ||
          !Array.isArray(row.original_official_pages)) {
        throw new Error('Unsafe or duplicate source candidate row.');
      }
      seen.add(row.candidate_id);
    }
    return book;
  }

  function validateSession(raw, book) {
    assertBook(book);
    if (!raw || typeof raw !== 'object' || Array.isArray(raw) ||
        Object.keys(raw).sort().join('|') !==
          'entries|saved_at|schema_version|source_casebook_sha256|status' ||
        raw.schema_version !== 1 ||
        raw.status !== 'private_research_notes_not_wildfire_labels' ||
        raw.source_casebook_sha256 !== book.source_casebook_sha256 ||
        typeof raw.saved_at !== 'string' ||
        !Number.isFinite(Date.parse(raw.saved_at)) ||
        !Array.isArray(raw.entries) || raw.entries.length > book.rows.length) {
      throw new Error('Session schema, source fingerprint, or entry count differs.');
    }
    const ids = new Set(book.rows.map(row => row.candidate_id));
    const values = Object.create(null);
    for (const item of raw.entries) {
      if (!item || typeof item !== 'object' || Array.isArray(item) ||
          Object.keys(item).sort().join('|') !== 'candidate_id|note|work_state' ||
          !ids.has(item.candidate_id) ||
          Object.hasOwn(values, item.candidate_id) ||
          !STATES.includes(item.work_state) ||
          typeof item.note !== 'string' || item.note.length > LIMIT_NOTE) {
        throw new Error('Unknown case, duplicate entry, or unsupported work-state/note.');
      }
      values[item.candidate_id] = {work_state: item.work_state, note: item.note};
    }
    return values;
  }

  function makeSession(book, values, now) {
    assertBook(book);
    const entries = book.rows.map(row => {
      const value = values[row.candidate_id] || {work_state: 'not_started', note: ''};
      return {candidate_id: row.candidate_id, work_state: value.work_state,
              note: value.note};
    });
    const draft = {schema_version: 1,
                   status: 'private_research_notes_not_wildfire_labels',
                   source_casebook_sha256: book.source_casebook_sha256,
                   saved_at: now, entries};
    validateSession(draft, book);
    return draft;
  }

  function findRows(book, values, query = '', priority = 'all', work = 'all') {
    assertBook(book);
    const term = String(query).toLocaleLowerCase().trim();
    return book.rows.filter(row => {
      if (priority !== 'all' && row.priority_group !== priority) return false;
      if (work !== 'all' &&
          (values[row.candidate_id]?.work_state || 'not_started') !== work) return false;
      if (!term) return true;
      const fields = [
        row.candidate_id, row.mtbs?.name, row.mtbs?.fire_id,
        row.nifc?.name, row.nifc?.source_identity,
        ...row.original_official_pages.map(o => o.source_name),
        row.priority_group, row.next_action
      ];
      return fields.some(value => String(value || '').toLocaleLowerCase().includes(term));
    });
  }

  function mount(doc, book) {
    assertBook(book);
    const get = id => doc.getElementById(id);
    const values = Object.create(null);
    for (const row of book.rows) values[row.candidate_id] = {work_state:'not_started', note:''};
    let selected = book.rows[0].candidate_id;
    const element = (tag, text, className) => {
      const n = doc.createElement(tag);
      if (text !== undefined) n.textContent = String(text);
      if (className) n.className = className;
      return n;
    };
    const announce = msg => { get('flash').textContent = msg; };
    const field = (label, body) => {
      const box = element('div', undefined, 'source');
      box.append(element('strong', label), body);
      return box;
    };
    get('source-hash').textContent = book.source_casebook_sha256;
    const metrics = get('queue-counts');
    metrics.append(
      element('p', book.rows.length + ' candidates'),
      element('p', book.ambiguous_original_candidates + ' multiple-page cases'),
      element('p', book.original_official_page_population + ' distinct original CAL FIRE pages')
    );
    for (const [key, value] of Object.entries(book.manual_work_priority_counts)) {
      if (!value) continue;
      const item = element('option', key.replaceAll('_', ' ') + ' (' + value + ')');
      item.value = key;
      get('priority').append(item);
    }

    function renderList() {
      const list = get('case-list'); list.replaceChildren();
      const rows = findRows(book, values, get('search').value, get('priority').value,
                            get('work-state').value);
      get('visible-count').textContent = rows.length + ' of ' + book.rows.length +
                                        ' candidates shown; ordering is work priority, not fire risk.';
      for (const row of rows) {
        const li = element('li');
        const button = element('button');
        button.type = 'button';
        button.setAttribute('aria-pressed', String(row.candidate_id === selected));
        button.append(element('strong', row.mtbs.name || row.candidate_id),
                      element('small', row.candidate_id),
                      element('small', row.priority_reason),
                      element('small', 'Pages: ' + row.original_lead_count +
                              ' · ' + LABELS[values[row.candidate_id].work_state]));
        button.addEventListener('click', () => {
          selected = row.candidate_id;
          renderList(); renderDetail();
          get('detail').focus();
        });
        li.append(button); list.append(li);
      }
      if (!rows.length) list.append(element('li', 'No research cases match these filters.'));
    }

    function renderDetail() {
      const row = book.rows.find(r => r.candidate_id === selected);
      if (!row) return;
      const box = get('detail'); box.replaceChildren();
      box.append(element('h2', row.mtbs.name || row.candidate_id),
                 element('p', row.candidate_id + ' · manual work group: ' +
                         row.priority_group, 'status'),
                 element('p', row.priority_reason),
                 element('p', 'Next action: ' + row.next_action),
                 element('p', 'NO independently verified wildfire identity or nonfire label.',
                         'warning'));

      const identity = element('section');
      identity.append(element('h3', 'Retrospective source identities'),
                      element('p', 'MTBS: ' + row.mtbs.fire_id + ' · ' +
                              (row.mtbs.name || 'unnamed') +
                              ' · retrospective day: ' +
                              (row.mtbs.retrospective_day || 'not recorded')),
                      element('p', 'NIFC: ' + row.nifc.source_identity +
                              ' · ' + (row.nifc.name || 'unnamed')),
                      element('p', 'Neither name, date nor proximity authenticates same-event identity.'));
      box.append(identity);

      const pages = element('section');
      pages.append(element('h3', 'Original CAL FIRE candidate-linked pages'));
      if (!row.original_official_pages.length) {
        pages.append(element('p', 'No name-linked original CAL FIRE page in this subset. ' +
                         'Not evidence of wildfire absence or full CAL FIRE coverage.', 'warning'));
      }
      for (const page of row.original_official_pages) {
        const area = element('article', undefined, 'source');
        const headline = element('strong', page.source_name);
        area.append(headline);
        const link = element('a', page.source_url);
        if (/^https:\/\/[^\s/]+/.test(page.source_url)) {
          link.href = page.source_url;
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
        }
        area.append(element('p'), link,
                    element('p', 'Source date: ' + (page.source_day || 'unknown') +
                            ' · county: ' + (page.source_county || 'unknown')),
                    element('p', 'Retrospective MTBS gap: ' +
                            (page.mtbs_day_gap_not_decision_time ?? 'unknown') +
                            ' days · source-point distance: ' +
                            (page.distance_km_not_fire_identity ?? 'unknown') + ' km'),
                    element('p', 'Referenced by ' + page.reused_by_candidate_pairs +
                            ' candidate pair(s) · source SHA: ' +
                            page.source_detail_html_sha256));
        if (page.reused_by_candidate_pairs > 1)
          area.append(element('p', 'Shared official page: not independent corroboration.',
                              'warning'));
        const flags = element('ul');
        for (const flag of page.source_issues) flags.append(element('li', flag));
        if (page.source_issues.length) area.append(flags);
        pages.append(area);
      }
      box.append(pages);

      const provenance = element('section');
      provenance.append(element('h3', 'Blind reviewer and document lineage'),
                        element('p', 'Review relation: ' + (row.review_status || 'not conducted') +
                                ' · lineage: ' + row.lineage_status),
                        element('p', 'Archived private documents: ' + row.private_document_count),
                        element('p', 'Agreed source-lead hypothesis: ' +
                                (row.review_hypothesis || 'none') +
                                ' (never authenticated event identity)'));
      const citations = element('ul');
      for (const ref of row.review_citations) {
        citations.append(element('li', ref.reviewer + ': ' + ref.citation_url +
                         ' · matching receipts: ' + ref.matching_receipt_count));
      }
      provenance.append(citations);
      const gates = element('ul');
      for (const reason of row.unresolved_evidence_gates)
        gates.append(element('li', reason));
      if (!row.unresolved_evidence_gates.length)
        gates.append(element('li', 'Structural evidence checks may be complete; ' +
                            'physical event identity and upstream provenance remain unverified.'));
      provenance.append(element('h3', 'Outstanding evidence gates'), gates);
      box.append(provenance);

      const work = element('section');
      work.append(element('h3', 'Private research notes'));
      const stateLabel = element('label', 'Work state');
      const select = element('select');
      for (const status of STATES) {
        const item = element('option', LABELS[status]);
        item.value = status;
        select.append(item);
      }
      select.value = values[row.candidate_id].work_state;
      select.addEventListener('change', () => {
        values[row.candidate_id].work_state = select.value;
        renderList();
        announce('Work state changed in memory only. Export notes to preserve it.');
      });
      stateLabel.append(select);
      const noteLabel = element('label', 'Evidence gaps, URLs to authenticate, and next steps');
      const textarea = element('textarea');
      textarea.maxLength = LIMIT_NOTE;
      textarea.value = values[row.candidate_id].note;
      textarea.addEventListener('input', () => {
        values[row.candidate_id].note = textarea.value;
        announce('Notes changed in memory only. Export to save.');
      });
      noteLabel.append(textarea);
      work.append(stateLabel, noteLabel,
                  element('p', 'Research tracking is not a fire/nonfire label. ' +
                          'External adjudication requested is not adjudication completed.',
                          'warning'));
      box.append(work);
    }

    get('search').addEventListener('input', renderList);
    get('priority').addEventListener('change', renderList);
    get('work-state').addEventListener('change', renderList);

    function saveText(filename, text) {
      const blob = new Blob([text], {type:'application/json'});
      const link = element('a');
      const url = URL.createObjectURL(blob);
      link.href = url; link.download = filename;
      doc.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    get('download-session').addEventListener('click', () => {
      try {
        const session = makeSession(book, values, new Date().toISOString());
        saveText('private-wildfire-research-session.json',
                 JSON.stringify(session, null, 2) + '\n');
        announce('Downloaded local research notes. Keep the file private.');
      } catch (err) { announce('Export rejected: ' + err.message); }
    });
    get('session-file').addEventListener('change', async event => {
      const file = event.target.files?.[0];
      if (!file) return;
      try {
        if (file.size > MAX_SESSION_BYTES)
          throw new Error('Private session file exceeds bounded size.');
        const imported = validateSession(JSON.parse(await file.text()), book);
        for (const row of book.rows) {
          values[row.candidate_id] = imported[row.candidate_id] ||
            {work_state:'not_started', note:''};
        }
        renderList(); renderDetail();
        announce('Private session imported, bound to this exact original-source casebook.');
      } catch (err) { announce('Import rejected: ' + err.message); }
      finally { event.target.value = ''; }
    });
    renderList();
    renderDetail();
  }

  root.WildfireResearch = Object.freeze({
    assertBook, findRows, validateSession, makeSession, mount, STATES
  });
})(globalThis);
