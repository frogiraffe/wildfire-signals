# Public FIRMS research archive

The regular `/api/snapshot` map feed stays in Cloudflare Workers KV and expires.
When the `ENABLE_ANALYSIS_ARCHIVE=true` repository variable is set, eligible
scheduled collections at 00, 06, 12 and 18 UTC also retain individual FIRMS
thermal detections outside KV. Eligibility starts at minute 17. Manual repair
runs and other hours do not publish research evidence.

The collector writes a gzip JSONL file per successful FIRMS source. Each row
includes the original CSV fields, observation and receipt times, coordinates,
FRP, confidence, pixel size, source ID, SHA-256 and NASA data-use URL. A separate
scan receipt lists both source states and checksums of every pixel file, so an
empty successful response remains distinct from a source failure. The Files
are uploaded as a 90-day Actions artifact. FIRMS files and their scan receipt
are also published to a public GitHub prerelease tagged
`analysis-evidence-YYYY-MM-DD`. The uploader checks SHA-256 before upload and
refuses to replace an existing asset with different bytes. Daily assets are
append-only in normal operation; repository administrators retain the ability
to change or delete releases.

Agency research receipts remain temporary Actions artifacts pending a separate
rights and provenance review. The release archive is source evidence, not
confirmed fire identity, burned area, fire spread, or forecast validation.

To audit one day, download its GitHub Release assets and verify each pixel
file's SHA-256 against `pixel_files` in the scan receipt. A collection run is
accepted as archived only after the Release contains the receipt and its
listed files. A green collector job without an eligible archive window means
only the KV snapshot was updated.
