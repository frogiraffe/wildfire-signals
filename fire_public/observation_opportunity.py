"""Conservative cell/interval evidence state; no state is a fire-negative label."""
from __future__ import annotations

STATES = {
    "archived_candidate": "At least one original thermal record is archived for the unit.",
    "retrieval_failed": "The provider retrieval failed; archived silence is uninterpretable.",
    "retrieval_deferred": "The provider retrieval was deferred; archived silence is uninterpretable.",
    "publication_delayed": "Requested product was not yet available for the interval.",
    "no_reported_detection": "Independent acquisition evidence covers the unit and a complete product reports no detection; this is not no fire.",
    "no_confirmed_opportunity": "Independent acquisition evidence shows no relevant acquisition for the unit.",
    "no_archived_record_unverified_opportunity": "A successful retrieval returned no archived record for the unit, but acquisition opportunity is unknown.",
    "unknown": "No sufficient source or acquisition evidence for the unit."
}


def classify_interval(*, archived_candidates: int | None,
                      retrieval: str | None, acquisition: str = "unknown",
                      acquisition_evidence_sha256: str | None = None,
                      publication_delayed: bool = False) -> str:
    """Never infer a no-detection state from hotspots or a successful request alone."""
    if archived_candidates is not None and (type(archived_candidates) is not int or archived_candidates < 0):
        raise ValueError("candidate count must be a nonnegative integer or unknown")
    if retrieval not in (None, "complete", "failed", "deferred"):
        raise ValueError("invalid provider retrieval state")
    if acquisition not in ("unknown", "verified", "absent"):
        raise ValueError("invalid acquisition evidence state")
    if acquisition != "unknown" and (not isinstance(acquisition_evidence_sha256, str) or
        len(acquisition_evidence_sha256) != 64 or any(c not in "0123456789abcdef" for c in acquisition_evidence_sha256)):
        raise ValueError("independent acquisition evidence hash required")
    if acquisition == "absent" and archived_candidates:
        raise ValueError("archived candidate contradicts absent acquisition evidence")
    if archived_candidates:
        return "archived_candidate"
    if retrieval == "failed":
        return "retrieval_failed"
    if retrieval == "deferred":
        return "retrieval_deferred"
    if publication_delayed:
        return "publication_delayed"
    if acquisition == "absent":
        return "no_confirmed_opportunity"
    if acquisition == "verified" and retrieval == "complete" and archived_candidates == 0:
        return "no_reported_detection"
    if retrieval == "complete" and archived_candidates == 0:
        return "no_archived_record_unverified_opportunity"
    return "unknown"
