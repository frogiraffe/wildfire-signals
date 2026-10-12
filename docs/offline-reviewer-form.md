# Interactive offline independent reviewer form

Previously, reviewers received a readable HTML packet and a separate JSON template that needed manual editing. This feature produces a **self-contained interactive HTML packet** that works when opened directly from disk, without a local server or any deployment.

## Generate private reviewer files

Keep the source queue, packets and vote files outside the public Git repository.

    python -m fire_public.review_form \
      --queue /private/wildfire/unadjudicated-queue.json \
      --reviewer-id researcher-a \
      --html /private/wildfire/researcher-a.html

Generate another file for researcher B with their own identity. Share **only that person's packet**, never the other person's saved vote JSON.

Open the HTML in any supported desktop/mobile browser and decide every case:
- **Positive**: cite independently checked wildfire evidence using HTTPS.
- **Negative**: only available for independently enumerated sampling-frame units. **Not offered for retrospective NIFC leads**. This is not a judgment that the frame unit is fire-free; a reviewer must investigate actual independent evidence.
- **Abstain**: enter a descriptive reason of at least eight characters if evidence is insufficient or conflicting.

Every actual vote needs an affirmative personal evidence checkbox and an HTTPS evidence URL. On **Validate and download private votes JSON**, the browser downloads a file matching the established independent reviewer intake schema. The client records the *export-time reviewer attestation* time. Source issue/availability times must be separately checked by the coordinator.

**There is no autosave.** Save by downloading the vote JSON. Move it from the browser downloads directory to private storage before continuing. The generated HTML uses a SHA-256-pinned Content Security Policy, no external dependencies, no browser persistence and no scripted network requests. Opening an external evidence URL manually, if needed, is the researcher's separate action.

The interface is only a private input mechanism. It cannot verify identities, independent reviewer behavior, source completeness, or genuine non-fire windows. Existing Python reconciliation and cohort eligibility checks still make the final decisions.

## Reconcile exported votes

    python -m fire_public.review_intake details-template \
      --queue /private/wildfire/unadjudicated-queue.json \
      --output /private/wildfire/coordinator-details.json

    python -m fire_public.review_intake reconcile \
      --queue /private/wildfire/unadjudicated-queue.json \
      --first /private/wildfire/researcher-a-votes.json \
      --second /private/wildfire/researcher-b-votes.json \
      --details /private/wildfire/coordinator-details.json \
      --protocol /private/wildfire/protocol.json \
      --reviews /private/wildfire/reviews.json \
      --report /private/wildfire/reconciliation.json

Disagreements and abstentions remain unresolved; they are not silently converted into training labels. Cohort export and baseline evaluation continue through the existing independent label review workbench.

## Tests

    python -m unittest discover -s tests -p 'test_review_form.py' -v
    node tests/browser/review-form-local.mjs

The browser test opens a **real generated file:// form** on desktop/mobile, checks source-name XSS isolation, disabled NIFC negative option, missing/invalid field rejection, downloaded JSON schema and absence of network fetches. The Python tests verify restrictive CSP, private output protections and existing vote validator compatibility.

**Science gate:** usability improvement to an experimental review workflow. It does not create real independently verified fire-negative cases or measure a wildfire forecasting model's accuracy.
