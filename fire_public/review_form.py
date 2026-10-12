"""Private, self-contained interactive reviewer packet; no HTTP server needed.

The only output of browser interaction is a locally downloaded vote JSON that
must pass the existing independent-review intake and adjudication gates.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
from pathlib import Path

from .review_intake import _queue
from .label_review import _text, _write_new

STYLE = """
:root{color-scheme:light;font-family:system-ui,sans-serif;background:#f5f7f8;color:#142a34}
body{max-width:900px;margin:0 auto;padding:20px;line-height:1.5}
header,article,footer{background:white;border:1px solid #b8c6ca;border-radius:9px;padding:16px;margin:12px 0}
h1{font-size:1.5rem}h2{font-size:1.1rem;margin:0 0 8px}
label{display:block;font-weight:600;margin:9px 0}
select,input{width:100%;box-sizing:border-box;min-height:38px;padding:8px;
border:1px solid #8a9fa5;border-radius:5px;font-size:1rem}
button{border:0;border-radius:6px;background:#174b5e;color:white;padding:12px 20px;
font-weight:700;cursor:pointer}
button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #cd713c}
.notice{color:#724118}small{color:#344b56}code{overflow-wrap:anywhere}
.check{display:flex;align-items:center;gap:10px}.check input{width:20px;height:20px}
section{margin-top:10px}.hidden{display:none}#errors{white-space:pre-wrap;color:#8c1421}
@media(max-width:650px){body{padding:8px}header,article,footer{padding:10px}}
"""

SCRIPT = r"""
'use strict';
const packed = 'BOOTSTRAP_BASE64_VALUE';
const raw = atob(packed);
const bytes = Uint8Array.from(raw, ch => ch.charCodeAt(0));
const data = JSON.parse(new TextDecoder('utf-8').decode(bytes));
const place = document.getElementById('cases');
const controls = [];
document.getElementById('reviewer').textContent = data.reviewer_id;
document.getElementById('digest').textContent = data.queue_sha256;
document.getElementById('count').textContent = String(data.cases.length);
function node(tag, text, cls) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (cls) el.className = cls;
  return el;
}
function field(section, labelText, type, placeholder) {
  const wrapper = node('label', labelText);
  const el = document.createElement(type);
  if (type === 'input') {
    el.type = 'text';
    el.placeholder = placeholder || '';
    el.autocomplete = 'off';
  }
  wrapper.append(el);
  section.append(wrapper);
  return el;
}
for (const c of data.cases) {
  const article = node('article');
  article.append(node('h2', c.case_id));
  if (c.kind === 'retrospective_official_perimeter_review') {
    article.append(node('p','Retrospective US NIFC source lead; fire year ' +
      String(c.source_fire_year) + '; ObjectID ' + String(c.source_object_id) +
      '; reported incident ' + String(c.source_name || '(missing)') +
      '. Fire year is NOT an ignition date, and this is NOT independent adjudication.'));
  } else {
    article.append(node('p','Independently provided frame candidate: ' +
      String(c.region_id) + ', ' + String(c.latitude) + ', ' +
      String(c.longitude) + ', decision time ' + String(c.decision_at) +
      '. No fire-free status is implied.'));
  }
  const vote = field(article, 'Independent decision', 'select');
  for (const [value, label] of [
    ['unreviewed', 'Not reviewed'],
    ['vote1', 'Positive: independently supported fire'],
    ...(c.kind === 'independent_frame_review' ?
      [['vote0', 'Negative: independent complete outcome check']] : []),
    ['abstain', 'Abstain / insufficient evidence']
  ]) {
    const opt = document.createElement('option');
    opt.value = value;
    opt.textContent = label;
    vote.append(opt);
  }
  const evidence = field(article, 'Independent evidence URL (required for a vote)', 'input',
                         'https://source.example/.../record');
  evidence.inputMode = 'url';
  const check = node('label', undefined, 'check');
  const verified = document.createElement('input');
  verified.type = 'checkbox';
  check.append(verified, node('span', 'I personally reviewed independent evidence for this case'));
  article.append(check);
  const reason = field(article, 'Abstention reason (at least 8 characters)', 'input',
                       'Why can this case not be adjudicated?');
  controls.push({caseId:c.case_id, vote, evidence, verified, reason, kind:c.kind});
  place.append(article);
}
const message = document.getElementById('errors');
document.getElementById('export').addEventListener('click', () => {
  const errors = [];
  const votes = controls.map((c, i) => {
    const record = {case_id:c.caseId};
    const status = c.vote.value;
    if (status === 'abstain') {
      record.status = 'abstain';
      record.reason = c.reason.value.trim();
      if (record.reason.length < 8) errors.push('Case ' + (i+1) + ': abstention needs a reason.');
    } else if (status === 'vote0' || status === 'vote1') {
      const u = c.evidence.value.trim();
      let valid = false;
      try {
        const parsed = new URL(u);
        valid = parsed.protocol === 'https:' && Boolean(parsed.hostname);
      } catch (_) {}
      if (!c.verified.checked || !valid)
        errors.push('Case ' + (i+1) + ': confirm independent review and HTTPS evidence.');
      if (status === 'vote0' && c.kind !== 'independent_frame_review')
        errors.push('Case ' + (i+1) + ': historical perimeter cannot become fire-free.');
      record.status = 'vote';
      record.reviewer_label = status === 'vote1' ? 1 : 0;
      record.independent_evidence_checked = c.verified.checked;
      record.evidence_url = u;
      // This is the exporter's explicit attestation timestamp, not source publication time.
      record.reviewed_at = new Date().toISOString();
    } else {
      errors.push('Case ' + (i+1) + ': vote or explicitly abstain.');
    }
    return record;
  });
  if (errors.length) {
    message.textContent = errors.join('\n');
    document.getElementById('status').textContent =
      'No vote file exported. Correct the listed fields.';
    return;
  }
  message.textContent = '';
  const output = {
    schema_version:1,queue_sha256:data.queue_sha256,
    reviewer_id:data.reviewer_id,votes
  };
  const blob = new Blob([JSON.stringify(output, null, 2) + '\n'],
                        {type:'application/json'});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'wildfire-votes-' +
    data.reviewer_id.replace(/[^a-z0-9_-]/gi, '_') + '.json';
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 3000);
  document.getElementById('status').textContent =
    'Private vote file exported. Store it outside the public repository.';
});
"""


def render_form(queue_path: Path, reviewer_id: str) -> str:
    queue, cases, digest = _queue(queue_path)
    reviewer = _text(reviewer_id, "reviewer identity")
    payload = {
        "queue_sha256": digest, "reviewer_id": reviewer,
        "cases": [
            {key: case.get(key) for key in (
                "case_id", "kind", "source_fire_year", "source_object_id",
                "source_name", "region_id", "latitude", "longitude", "decision_at")}
            for case in cases.values()
        ],
    }
    packed = base64.b64encode(json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")).encode()).decode("ascii")
    script = SCRIPT.replace("BOOTSTRAP_BASE64_VALUE", packed)
    css_hash = base64.b64encode(hashlib.sha256(STYLE.encode()).digest()).decode()
    script_hash = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    csp = ("default-src 'none'; img-src 'none'; connect-src 'none'; "
           "object-src 'none'; base-uri 'none'; form-action 'none'; "
           "style-src 'sha256-" + css_hash + "'; "
           "script-src 'sha256-" + script_hash + "'")
    e = lambda value: html.escape(str(value), quote=True)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="' + e(csp) + '">'
        '<title>Private independent wildfire review</title>'
        "<style>" + STYLE + "</style></head><body>"
        "<header><h1>Independent wildfire review</h1>"
        '<p>Reviewer: <strong id="reviewer"></strong></p>'
        '<p>Queue digest: <code id="digest"></code> · Cases: <span id="count"></span></p>'
        '<p class="notice">All cases start unlabeled. No decision is prefilled. '
        "Official retrospective polygons do not establish fire occurrence dates. "
        "Only your own independent evidence supports a vote. "
        "This HTML runs offline and does not transmit answers; downloading the JSON "
        "is required to save work. Closing this page loses unsaved responses.</p>"
        "</header><main id=\"cases\"></main><footer>"
        '<p class="notice">The downloaded vote is an attestation, not independent '
        "source authentication. A second reviewer must independently vote; "
        "coordinator and negative-window coverage checks happen separately.</p>"
        '<button type="button" id="export">Validate and download private votes JSON</button>'
        '<p role="alert" id="errors"></p><p role="status" id="status"></p>'
        "</footer><script>" + script + "</script></body></html>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a completely offline, blind and self-contained reviewer form")
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--html", type=Path, required=True)
    args = parser.parse_args()
    if args.html.resolve() == args.queue.resolve() or args.html.exists():
        parser.error("output must be new and must never replace source queue")
    result = render_form(args.queue, args.reviewer_id)
    _write_new(args.html, result)
    print(json.dumps({"html": str(args.html), "reviewer_id": args.reviewer_id,
                      "source_queue_sha256": hashlib.sha256(
                          args.queue.read_bytes()).hexdigest()}, sort_keys=True))


if __name__ == "__main__":
    main()
