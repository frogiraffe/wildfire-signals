# Durable private agency source receipt vault

**Status: offline recovery feature / experimental research.** This feature preserves original prospective NIFC and CWFIS source receipt `agency-*.json.gz` bytes. It solves one concrete weakness of the earlier time machine: temporary GitHub Actions artifacts expire after **up to 90 days**, so analysts must download and preserve them before expiry. No remote storage is created or configured, no new paid account is required, and nothing is published to the GitHub repository or public map.

## Workflow: original sources → vault → portable backup → historical time machine

First enable and successfully run prospective receipts according to [the original opt-in collection design](prospective-agency-receipts-2026-10-12.md). Only then download your permitted GitHub Actions `agency-*.json.gz` files into a **private local directory outside the Git checkout**. Synthetic test receipts are not real fire labels.

```sh
# Preserve the source bytes, incrementally and safely.
python -m fire_public.agency_vault ingest \
  --input /private/downloaded-actions-receipts \
  --vault /private/wildfire-original-vault

# Audit original SHA-256, filename receipts, scan times, source failures/gaps.
python -m fire_public.agency_vault verify \
  --vault /private/wildfire-original-vault

# Export a portable, source-identical ZIP backup to a different local volume.
python -m fire_public.agency_vault export \
  --vault /private/wildfire-original-vault \
  --output /external-backup/wildfire-evidence-001.zip

# After simulated or real disk loss, recover the same original receipt bytes.
python -m fire_public.agency_vault restore \
  --bundle /external-backup/wildfire-evidence-001.zip \
  --vault /private/recovered-original-vault

# Reconstruct the existing event store solely from the recovered original evidence.
python -m fire_public.agency_vault rebuild \
  --vault /private/recovered-original-vault \
  --db /private/rebuilt-prospective-history.sqlite3

# Browse exactly what was known by a chosen time.
python -m fire_public.prospective_replay \
  --db /private/rebuilt-prospective-history.sqlite3 \
  --provider cwfis --output-dir /private/agency-replay-001
```

Each vault stores original gzip files under `receipts/`, **without altering their bytes**. Ingestion verifies the SHA-256 prefix embedded in each original filename, gzip bounds, schema, source states, timestamps and scan identity. Repeated import of identical data is idempotent; different evidence claiming the *same original scan UTC* fails. Source files are linked into the vault new-only (no replacement); a preflight and cleanup guard attempt to prevent partial writes. If a process or filesystem crashes unexpectedly, always rerun `verify` and investigate incomplete state before relying on it.

The ZIP contains an explicit `manifest.json` with the full 64-character SHA-256 for each original compressed file, source scan/receipt metadata, and zero verified fire or extinguishment labels, plus only the original files. Restore checks an allowlist of paths, exact ZIP member sets, compressed and uncompressed size budgets, digest equality, source audit rules, and restored manifest equivalence. There is **no extraction of untrusted ZIP member paths**. Import limits are at most 4,096 receipts / 256 MiB of original compressed data per vault and 128 KiB per receipt. Exports are new-only and ZIP members contain the original gzip bytes without recompression. Outputs remain private (new directory mode 0700, files mode 0600).

The restored SQLite is created from scratch with the existing `import_receipts` function; it has a `PRAGMA integrity_check` pass and publishes only after successful completion. Historical distinctions are maintained: complete source listing, failed/deferred agency source, and absence from current source layer; no event disappearance becomes extinguishment. NIFC/CWFIS identities are *not* linked by proximity.

## One-command research workspace from the archive

Once original receipts are in the vault, create a complete **offline as-of incident explorer** without retaining an intermediate SQLite file:

```sh
python -m fire_public.agency_vault workspace \\
  --vault /private/recovered-original-vault \\
  --provider cwfis \\
  --at 2026-10-12T15:00:00Z \\
  --output-dir /private/agency-research-session-002
```

The command verifies and imports the original receipts into a temporary private SQLite database, performs the same source-time replay as `fire_public.prospective_replay`, writes new-only `index.html` and `evidence.json`, then removes the temporary SQLite database. Add `--official-id` with `--provider` for a large archive. Omit `--at` to use the latest **captured** source receipt, not the computer's current time. There are **no automatic event labels, source joins, predictions or network calls**.

## Security and disaster recovery limitations

- **SHA-256 detects accidental or unsanctioned byte changes relative to the manifest.** Because the manifest is shipped alongside its contents and is not externally signed, it does **not** independently authenticate the origin of a governmental record, prove an event, provide a tamper-proof clock or survive an attacker who can replace the entire archive.
- A backup file **on the same failing disk is not durable**. Keep an offline second copy on a separate medium or storage location and preserve its SHA-256 independently; rehearse restoration. No automatic background backup or cloud synchronization is created by this PR.
- ZIP backup/restore handles *agency* source receipts. Existing FIRMS pixel evidence is a separate original receipt stream; it is not silently merged into this archive, nor are outcomes, perimeters, weather or satellite detections promoted into verified agency incidents.
- The archive is private and should **not be committed to public Git or published as GitHub Releases** until legal reuse rights, data privacy and provenance have been reviewed. File preservation does not create new source licenses.
- An original receipt created in the past but downloaded later still has its recorded receipt time. The vault cannot attest that an artifact was actually available locally before download. For decision-time modeling, check archival acquisition provenance; a stored timestamp alone cannot prove timeliness.

## Automated verification

```sh
python -m unittest discover -s tests -p 'test_agency_vault.py' -v
python -m unittest discover -s tests -p 'test_receipt_history.py' -v
python -m unittest discover -s tests -p 'test_prospective_replay.py' -v
```

Synthetic receipts exercise repeated and conflicting scans, corruption/tampering, ZIP traversal attempts, exact-byte restoration, database reconstruction, source outage vs. non-listing, before/after decision-time visibility, new-only private paths, and CLI operations.

**Important:** This does not automatically download expiring Actions artifacts. The irreversible first step of obtaining the original permitted records before expiration remains operator-controlled. Durable local preservation does not create an independent wildfire validation cohort or measured probability.
