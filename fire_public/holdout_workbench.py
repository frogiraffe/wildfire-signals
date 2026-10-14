"""Offline, deterministic, privacy-preserving holdout research workbench.

Consumes externally adjudicated rows: this tool neither creates labels nor trains
models. Emits an aggregate-only research eligibility report with input SHA-256.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
from .holdout_audit import audit_holdout, MAX_ROWS
from .labeled_evaluation import _manifest, _audit_rows

MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_LINE_BYTES = 32 * 1024


def _safe_file(path: Path, limit: int = MAX_INPUT_BYTES) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("input must be a regular file")
    if path.stat().st_size > limit:
        raise ValueError("input exceeds byte budget")
    return path.read_bytes()


def load_jsonl(path: Path):
    raw = _safe_file(path)
    rows = []
    for line in raw.splitlines():
        if len(line) > MAX_LINE_BYTES:
            raise ValueError("oversized JSONL row")
        if not line.strip():
            continue
        if len(rows) >= MAX_ROWS:
            raise ValueError("too many observations")
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError("each JSONL row must be an object")
        rows.append(item)
    return rows, hashlib.sha256(raw).hexdigest()


def _project(row):
    """Translate audited source contract without inferring unavailable fields."""
    return {
        "sampling_unit_id": row["case_sampling_id"],
        "event_id": row["event_id"],
        "region_id": row["region_id"],
        "feature_as_of": row["decision_at"],
        "feature_latest_available_at": row.get("feature_latest_available_at"),
        "label_available_at": row["label_available_at"],
        "label": row["label"],
        "split": row["split"],
    }


def run_report(cohort_path: Path, manifest_path: Path, *, embargo_hours=168):
    raw_manifest = _safe_file(manifest_path, 1024 * 1024)
    manifest = json.loads(raw_manifest)
    _manifest(manifest)
    rows, sha = load_jsonl(cohort_path)
    audited = _audit_rows(rows, manifest)
    # The upstream scientific contract may certify provenance based on a manifest
    # assertion. This report never upgrades that assertion to independent proof.
    projected = [_project(row) for row in rows]
    gates = audit_holdout(projected, embargo_hours=embargo_hours)
    return {
        "schema_version": 1,
        "report_type": "holdout_eligibility_not_prediction_skill",
        "scientific_tier": "experimental",
        "source": {
            "cohort_sha256": sha,
            "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
            "target_name": manifest["target_name"],
            "horizon_hours": manifest["horizon_hours"],
            "study_region": manifest["study_region"],
        },
        "cohort_audit": audited,
        "holdout": gates,
        "eligible_for_model_evaluation": gates["eligible_for_holdout_evaluation"],
        "independently_verified_ground_truth": False,
        "measured_model_skill": None,
        "limitations": [
            "Source documents and ground truth were not independently re-verified.",
            "No independent fire-negative observation can be inferred from missing FIRMS rows.",
            "Input split is supplied by the researcher and not optimized using test outcomes.",
            "Eligibility does not imply calibrated risk, wildfire confirmation or forecast validity.",
        ],
    }


def html_report(result):
    """Standalone readable report, with all user-controlled text escaped."""
    source = result["source"]
    gate = result["holdout"]
    status = "PASS" if result["eligible_for_model_evaluation"] else "BLOCKED"
    issues = "".join("<li>" + html.escape(reason) + "</li>" for reason in gate["failed_gates"])
    limitations = "".join("<li>" + html.escape(reason) + "</li>" for reason in result["limitations"])
    title = html.escape(source["target_name"])
    digest = html.escape(source["cohort_sha256"])
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">"
        "<title>Wildfire holdout evidence</title><style>"
        "body{font:16px system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:1rem;line-height:1.5}"
        "code{overflow-wrap:anywhere}section{border-top:1px solid #bbb;margin-top:1rem}"
        "</style></head><body><main><h1>Holdout research audit</h1>"
        "<p>Target: " + title + "</p><p>Evaluation eligibility: <strong>" + status + "</strong></p>"
        "<p>Train: " + str(gate["train_rows"]) + " | Test: " + str(gate["test_rows"]) + "</p>"
        "<p>Model skill: not measured. Independent ground truth: not re-verified.</p>"
        "<p>Source SHA-256: <code>" + digest + "</code></p>"
        "<section><h2>Failed gates</h2><ul>" + (issues or "<li>None at split level</li>") + "</ul></section>"
        "<section><h2>Scientific limitations</h2><ul>" + limitations + "</ul></section>"
        "</main></body></html>\n"
    )


def main():
    parser = argparse.ArgumentParser(description="Offline independent-label holdout audit")
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New report JSON output")
    parser.add_argument("--html", type=Path, help="Optional new offline HTML output")
    parser.add_argument("--embargo-hours", type=float, default=168)
    args = parser.parse_args()
    inputs = {args.cohort.resolve(), args.manifest.resolve()}
    outputs = [args.output] + ([args.html] if args.html else [])
    if len({p.resolve() for p in outputs}) != len(outputs):
        parser.error("outputs must be distinct")
    if any(p.resolve() in inputs or p.exists() or p.is_symlink() for p in outputs):
        parser.error("outputs cannot overwrite inputs or existing files")
    result = run_report(args.cohort, args.manifest, embargo_hours=args.embargo_hours)
    # Write only after full source validation and all eligibility computation.
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
    if args.html:
        with args.html.open("x", encoding="utf-8") as handle:
            handle.write(html_report(result))
    print(json.dumps({"status": "eligible" if result["eligible_for_model_evaluation"] else "blocked",
                      "json": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
