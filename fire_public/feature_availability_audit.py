"""Fail-closed as-of feature-availability audit for historical research cohorts.

This is a structural chronology check, not independent wildfire validation.
No outcomes, predictions or model performance are produced.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable


def _instant(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}: timezone-aware ISO-8601 timestamp required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field}: invalid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field}: timezone required")
    return parsed.astimezone(timezone.utc)


def audit_asof_features(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Audit rows with decision_at and a mapping of named feature evidence.

    Each feature must have value, observed_at, and available_at. Unknown values
    are permitted but make the case ineligible. Availability is the earliest
    verifiable availability, *not* the download time or acquisition time.
    Repeated case IDs, missing evidence or post-decision data fail closed.
    """
    seen: set[str] = set()
    cases: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError("case must be an object")
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in seen:
            raise ValueError(f"case {index}: unique nonempty case_id required")
        seen.add(case_id)
        decision = _instant(row.get("decision_at"), "decision_at")
        features = row.get("features")
        if not isinstance(features, dict) or not features:
            raise ValueError(f"case {case_id}: nonempty features mapping required")
        violations: list[str] = []
        for name, evidence in sorted(features.items()):
            if not isinstance(name, str) or not name.strip() or not isinstance(evidence, dict):
                raise ValueError(f"case {case_id}: invalid feature evidence")
            if evidence.get("value") is None:
                violations.append(f"{name}:unknown_value")
            instants = {}
            for field in ("observed_at", "available_at"):
                try:
                    at = _instant(evidence.get(field), f"{name}.{field}")
                except ValueError:
                    violations.append(f"{name}:invalid_{field}")
                    continue
                instants[field] = at
                if at > decision:
                    violations.append(f"{name}:{field}_after_decision")
            if (len(instants) == 2
                    and instants["available_at"] < instants["observed_at"]):
                violations.append(f"{name}:available_before_observed")
            source = evidence.get("source_id")
            if not isinstance(source, str) or not source.strip():
                violations.append(f"{name}:missing_source_id")
        cases.append({"case_id": case_id, "eligible": not violations,
                      "violations": violations})
    return {
        "schema_version": 1,
        "audit": "asof_feature_availability",
        "cases": cases,
        "total": len(cases),
        "eligible": sum(item["eligible"] for item in cases),
        "ineligible": sum(not item["eligible"] for item in cases),
        "scientific_status": "structural_audit_only",
        "model_training_authorized": False,
        "warning": "Chronology and source-id checks do not validate fire outcomes, satellite exposure, licensing or independent labels.",
    }
