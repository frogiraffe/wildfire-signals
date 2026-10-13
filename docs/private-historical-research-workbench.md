# Private historical wildfire evidence research workbench

This is an **experimental end-to-end offline research experience**, not a public wildfire alert and not a model for wildfire probability. It turns the original-source-replayed CAL FIRE, NIFC and MTBS 2018 pilot into a source-bound, inspectable human work queue that can save and resume research without an account or network.

## What it does

- **All** original geographic candidate pairs are retained, including zero CAL FIRE name leads and single-lead cases; multi-lead cases include the separate source-lineage investigation from [PR #45](calfire-source-lineage-audit.md).
- Every record exposes original MTBS/NIFC identifiers, CAL FIRE source pages with preserved SHA-256, available retrospective date/distance context, multiple-candidate page reuse, reviewer agreement/disagreement, documentary receipt availability, evidence gaps, and the **next useful research action**.
- Sorting is a **transparent workflow ordering**, not a probability of fire, importance, severity, or match likelihood. It prioritizes conflicting independent reviewer hypotheses, reuse of the same original incident page, citation/document gaps and unresolved competing pages, before unresolved single/no-page leads and dossiers ready for *external* adjudication.
- A self-contained accessible HTML file provides text search, workflow filters, evidence detail, links to original sources, research note-taking, and private **export/import** of JSON session notes.
- Browser notes are **memory-only** until explicitly exported. Import validates exact original-source casebook SHA and candidate IDs. It **cannot** mark event identity, fire absence or forecast accuracy as confirmed.
- Outputs are **private local-only**: new directory, mode 0700; files mode 0600; never written inside the public Git repository, never overwritten. HTML needs no internet resources and its CSP forbids scripts other than the bundled inline hashed application, network requests and form posts. Clicking government source links is an explicit browser navigation.

The queue keeps the global product distinct from its **bounded 2018 California evidence pilot**; no geographic production restriction was added.

## Example: archive-to-investigation workflow

With the exact original archived government files used in [CAL FIRE alternative dossiers](calfire-alternative-event-dossiers.md):

```sh
python -m fire_public.research_workbench \
  --study-dir /private/wildfire/california-2018 \
  --calfire-archive-dir /private/wildfire/calfire-2018 \
  --batch /private/wildfire/calfire-detail-batch-0 \
  --batch /private/wildfire/calfire-detail-batch-6 \
  --batch /private/wildfire/calfire-detail-batch-12 \
  --output-dir /private/wildfire/research-workbench-001
```

If **real independent reviewers and original documentary source receipts exist**, add `--first /private/alice-votes.json --second /private/bob-votes.json --private-receipts /private/wildfire/private-document-store`. Omitting them does *not* synthesize reviewers or evidence; the queue describes the missing investigative steps.

Open `/private/wildfire/research-workbench-001/index.html` locally. Search by incident name or original provider ID, pick a row, inspect authentic source URLs and structural gaps, then set a private *work state*: not started, investigating, blocked, or external adjudication requested. **None of these states imply a verified wildfire outcome.** Write next steps and use **Export private notes JSON** to retain them. In any newer bundle created from the **same exact original source casebook**, use the file chooser to resume your notes; a different source casebook fingerprint is rejected. There is no browser storage or network sync.

Three deterministic outputs are written: `queue.json`, `queue.csv` (spreadsheet formula-injection protected), and `index.html`. Source URLs/record names/notes are local private material. **Do not deploy the research workbench to the public map or upload these files to GitHub.**

## Scientific caveats

Original CAL FIRE pages are a **name-linked subset**, not a fire census. Repeated source links are not independent reporting. NIFC region candidates, final MTBS perimeters, CAL FIRE point coordinates, documented reviewer hypotheses and preserved third-party bytes **do not** prove same physical-event identity. Missing source leads are not verified nonfire controls. Retrospective source dates and final perimeters must not be substituted for historically available real-time predictor inputs. No predictive scores, probabilities or external-label promotion.

## Tests

```sh
python -m unittest discover -s tests -p 'test_research_workbench.py' -v
node --test tests/js/research-workbench.test.mjs
```

The GitHub workflow also reruns the upstream lineage and blind-review regression suites. All test incident pages, reviewer votes and external documents are explicitly synthetic fixtures; no human source adjudication has been conducted as part of the test.

## Actual browser smoke test (desktop and mobile)

The additional [Chromium smoke test](../tests/browser/research-workbench-local.mjs) constructs a full synthetic original-source-replayed research casebook using the same Python pipeline as the CLI, renders its local HTML, and opens it using a `file://` URL (not a web server). It checks real user actions on 1280 px desktop and 390 px mobile: case search, empty result, source detail, note/status edits, JSON export, session restore, rejection of a changed study fingerprint, HTML-in-note nonexecution, CSP restrictions, runtime exceptions and unexpected network requests.

```sh
npm ci
npx playwright install chromium
node tests/browser/research-workbench-local.mjs
```

The GitHub Actions browser job runs after the earlier Python/JS validation, with an ephemeral test-generated dataset. It does not access real private review artifacts, upload any sources, or change the live map.
