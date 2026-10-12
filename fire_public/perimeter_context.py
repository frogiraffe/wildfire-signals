"""Independent, retrospective perimeter context for historical evidence reports.

This never links an IFPH polygon to a present-day agency incident or FIRMS
pixel based on proximity and never creates negative or prospective features.
"""
from __future__ import annotations

from pathlib import Path

from .official_perimeters import report as perimeter_report, SERVICE, RIGHTS_URL

PREVIEW_LIMIT = 75


def historical_perimeter_context(path: str | Path, *, at: str,
                                 region: dict | None = None,
                                 year: int | None = None) -> dict:
    options = {"at": at, "year": year, "limit": PREVIEW_LIMIT}
    if region:
        if region["radius_km"] > 250:
            raise ValueError("retrospective perimeter spatial filter max radius is 250 km")
        options.update(latitude=region["latitude"],longitude=region["longitude"],
                       radius_km=region["radius_km"])
    result = perimeter_report(path, **options)
    examples = [{
        "source_identity": event["source_identity"],
        "fire_year":event["fire_year"],
        "name": event["name"],
        "source_reported_acres":event["source_reported_acres"],
        "feature_sha256":event["feature_sha256"],
        "captured_at":event["captured_at"],
        "batch_id":event["batch_id"],
    } for event in result["events"]]
    return {
        "evidence_kind":"nifc_retrospective_fire_perimeters",
        "provider":"nifc_ifph_retrospective",
        "jurisdiction":"USA",
        "source":SERVICE,"rights":RIGHTS_URL,
        "decision_at":result["decision_at"],
        "source_fire_year":year,
        "archive_known_source_id_count":result["visible_unique_source_ids"],
        "matched_polygons":result["matches"],
        "preview_count":len(examples),
        "preview_limit":PREVIEW_LIMIT,
        "preview_truncated":result["truncated"],
        "source_batch_subset_only":result["any_source_batch_subset_only"],
        "source_batches":result["source_batches"],
        "examples":examples,
        "negative_labels_created":0,
        "model_ready":False,
        "notes":[
            "Retrospective US government boundary evidence through 2019, not live incident or forecast data.",
            "A source year never means the polygon was captured or available to the model during that year.",
            "Source perimeter registry is incomplete; missing polygons never establish no wildfire.",
            "Polygons are never matched to agency active-layer incidents or FIRMS candidates by proximity.",
            "Locations are filtered using approximate geometry-circle intersection for exploration only.",
        ],
    }
