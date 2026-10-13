# Recover expiring prospective agency receipts from GitHub Actions

**Experimental, manually invoked, local-only sync.** The official scheduled collector uploads one Actions artifact with name `analysis-receipt-<run_id>-<attempt>`. That ZIP can contain NASA FIRMS research pixels **and optionally** one `agency-*.json.gz` receipt recording prospective NIFC/CWFIS source status. This sync ingests **only genuine original agency receipt bytes** into the [private archival vault](durable-agency-evidence-vault.md). Satellite pixels are **not** interpreted as official incident confirmations.

## Use on your own computer

Set a token with **Actions: read** permission on `frogiraffe/wildfire-signals`. Prefer a narrow-scoped token supplied via the shell environment, not a token in CLI arguments, repository files, screenshots or logs. Do not use production collector/Cloudflare secrets.

```sh
export GH_TOKEN="...your Actions-read credential..."
python -m fire_public.actions_agency_sync \
  --vault /private/wildfire-original-vault \
  --dry-run

# Explicitly pull the selected bounded set into the existing/new private vault.
python -m fire_public.actions_agency_sync \
  --vault /private/wildfire-original-vault \
  --pages 5 --max-downloads 32

# For a smaller rolling catch-up window:
python -m fire_public.actions_agency_sync \
  --vault /private/wildfire-original-vault \
  --since 2026-10-12T00:00:00Z --pages 5 --max-downloads 32

python -m fire_public.agency_vault verify \
  --vault /private/wildfire-original-vault

python -m fire_public.agency_vault export \
  --vault /private/wildfire-original-vault \
  --output /different-physical-disk/agency-backup-001.zip

python -m fire_public.agency_vault workspace \
  --vault /private/wildfire-original-vault --provider cwfis \
  --output-dir /private/research-workspace-001
```

The command uses GitHub REST read-only endpoints for artifact lists, exact run metadata and ZIP archive download. It verifies the uploader came from the **successful official `.github/workflows/collect.yml` job on `main`**, with a matching named run ID and provider-agnostic 40-digit commit SHA; the inner original receipt must match that run and have plausible original observation/capture times. Unknown, expired, oversized or contradictory source evidence is *not* silently labelled negative. Artifact ZIP contents are not arbitrarily extracted: only an allowlisted original root-level `agency-*.json.gz` member is validated and copied to a private temporary folder, then source-vault rules enforce non-overwrite and SHA integrity.

Download redirects are limited to official HTTPS Actions/Blob delivery hosts and **the GitHub token is never forwarded to the signed download destination**. The script only reads GitHub and writes the user-chosen **local** vault; it does not schedule itself, alter repository settings, write GitHub issues, publish sources, call Cloudflare, or create accounts. It never prints the token. Runs with no agency receipt (pixel-only evidence) are counted separately.

## Completeness and retention caveats

- Discovery scans at most 5 pages × 100 repository artifacts by default, with at most 32 **previously unchecked** ZIP downloads per invocation; use `--pages` and `--max-downloads` to widen. The `discovery_exhaustive`, `listing_page_cap_reached` and `outside_download_limit` fields communicate whether the requested search is complete. With a `--since` filter, a full historical discovery is **not** claimed.
- The sync keeps a local `.actions-sync-state.json` **progress index inside the private vault**. Each successful download is recorded with the immutable GitHub artifact ID. Original agency data is skipped only while the archived receipt still exists with its original SHA; a removed original is re-downloaded if the ZIP still exists. Pixel-only ZIPs are noted as checked without creating a fake agency receipt. A progress-only private vault can be created when an archive contains no agency originals. The index is bookkeeping, **not source evidence** and is not in the portable ZIP backup. Repeated bounded calls advance to older unchecked ZIPs rather than forever re-downloading the most recent set.
- **The ZIP artifacts expire (up to 90 days).** Sync only preserves *still available* originals. An expired or missing job artifact cannot be recreated or inferred from the current live map.
- Running a command once does not make backups ongoing. Run this locally at a regular cadence using your own scheduler if desired, but verify its logs and maintain an independent ZIP copy on another physical medium. This PR does **not** create a background job or ongoing automation.
- A green collector run does not prove an agency receipt was written. Collection can be skipped, research archiving is opt-in, and oversized records or source errors can prevent the original receipt. The program separately counts ZIP files with no agency original.
- The repository may have many other workflows and artifacts. The command searches only the exact expected collector artifact naming convention and rejects foreign runs; it does **not** download full repo archives or every artifact.
- The captured timestamp is the **collector's recorded time**, not cryptographic proof of original government source publication; the SHA proves byte integrity relative to archive metadata, not wildfire occurrence or independent fire outcome truth.

## Offline CI

```sh
python -m unittest discover -s tests -p 'test_actions_agency_sync.py' -v
```

Tests use synthetic receipts and mock GitHub metadata/download delivery, so they never require a token or Internet connection.
