"""CMR granule metadata is context, never a negative-observation mask."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from fire_public.acquisition_catalog import build_catalog_report, catalog_url
from fire_public.collect import FIRMS_SOURCES
from fire_public.historical_rollup import build_rollup
from fire_public.pixel_history import import_release_assets
from test_pixel_history import make_release, pixel


REGION = {"region_id": "PILOT", "latitude": 37.929, "longitude": 41.1166, "radius_km": 25}


def bundle(entries_by_product):
    queries = []
    for product in ("VJ103IMG_NRT", "VJ203IMG_NRT"):
        body = json.dumps({"feed": {"entry": entries_by_product.get(product, [])}})
        queries.append({"product": product, "url": catalog_url(product, "2026-10-10", "2026-10-11",
                        "40.8,37.6,41.5,38.3"), "cmr_hits": len(entries_by_product.get(product, [])),
                        "response_sha256": hashlib.sha256(body.encode()).hexdigest(), "body": body})
    return {"schema_version": 1, "fetched_at": "2026-10-14T12:00:00+00:00", "queries": queries}


def granule(product, start, end, identifier):
    return {"id": identifier, "producer_granule_id": f"{product}.A2026283.1000.021.sample.nc",
            "collection_concept_id": "C123-LANCEMODIS", "time_start": start,
            "time_end": end, "updated": "2026-10-10T12:00:00.000Z",
            "polygons": [["40 37 40 38 42 38 42 37 40 37"]]}


class AcquisitionCatalogTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.db = root / "pixels.sqlite3"
        captured = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
        make_release(root / "scan", captured, [
            pixel(FIRMS_SOURCES[0], when=datetime(2026, 10, 10, 10, 3, tzinfo=timezone.utc),
                  latitude=37.94, longitude=41.12, ident="one"),
            pixel(FIRMS_SOURCES[1], when=datetime(2026, 10, 11, 9, 15, tzinfo=timezone.utc),
                  latitude=37.94, longitude=41.12, ident="two")])
        import_release_assets(self.db, root)
        build_rollup(self.db, [REGION])

    def test_catalog_temporal_matches_do_not_verify_cell_opportunity(self):
        source = bundle({"VJ103IMG_NRT": [granule("VJ103IMG_NRT", "2026-10-10T10:00:00.000Z",
                                    "2026-10-10T10:06:00.000Z", "G1-LANCEMODIS")],
                         "VJ203IMG_NRT": [granule("VJ203IMG_NRT", "2026-10-11T09:18:00.000Z",
                                    "2026-10-11T09:24:00.000Z", "G2-LANCEMODIS")]})
        report = build_catalog_report(self.db, [REGION], source, start_date="2026-10-10",
                                      end_date="2026-10-11", bbox="40.8,37.6,41.5,38.3")
        self.assertEqual(report["population"]["archived_raw_pixels"], 2)
        self.assertEqual(report["population"]["candidate_provider_minutes"], 2)
        self.assertEqual(report["population"]["temporally_matched_candidate_provider_minutes"], 1)
        self.assertEqual(report["candidate_provider_minutes"][0]["catalog_granule_ids"], ["G1-LANCEMODIS"])
        self.assertEqual(report["candidate_provider_minutes"][1]["catalog_granule_ids"], [])
        self.assertFalse(report["observation_opportunity_verified"])
        self.assertIsNone(report["catalog_first_available_at"])
        self.assertIsNone(report["no_detection_count"])
        self.assertEqual(report, build_catalog_report(self.db, [REGION], source,
                         start_date="2026-10-10", end_date="2026-10-11", bbox="40.8,37.6,41.5,38.3"))

    def test_incomplete_or_tampered_catalog_fails_closed(self):
        source = bundle({})
        source["queries"][0]["body"] += " "
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_catalog_report(self.db, [REGION], source, start_date="2026-10-10",
                                 end_date="2026-10-11", bbox="40.8,37.6,41.5,38.3")
        source = bundle({})
        source["queries"][0]["cmr_hits"] = 101
        with self.assertRaisesRegex(ValueError, "incomplete"):
            build_catalog_report(self.db, [REGION], source, start_date="2026-10-10",
                                 end_date="2026-10-11", bbox="40.8,37.6,41.5,38.3")

    def test_wrong_satellite_and_future_report_window_rejected(self):
        source = bundle({"VJ103IMG_NRT": [granule("VNP03IMG_NRT", "2026-10-10T10:00:00.000Z",
                                     "2026-10-10T10:06:00.000Z", "G1-LANCEMODIS")]})
        with self.assertRaisesRegex(ValueError, "product"):
            build_catalog_report(self.db, [REGION], source, start_date="2026-10-10",
                                 end_date="2026-10-11", bbox="40.8,37.6,41.5,38.3")

    def test_published_real_cmr_snapshot_and_report_are_content_addressed(self):
        root = Path(__file__).resolve().parents[1]
        snapshot = json.loads((root / "docs/research/source-samples/batman-cmr-2026-10-09-11.json").read_text())
        report = json.loads((root / "public/data/batman-cmr-context-2026-10-11.json").read_text())
        for query in snapshot["queries"]:
            self.assertEqual(hashlib.sha256(query["body"].encode()).hexdigest(),
                             query["response_sha256"])
        digest = report.pop("evidence_sha256")
        canonical = (json.dumps(report, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False, allow_nan=False) + "\n").encode()
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), digest)
        self.assertEqual(report["population"]["catalog_granules"], 20)
        self.assertEqual(report["population"]["candidate_provider_minutes"], 7)
        self.assertEqual(report["population"]["archived_raw_pixels"], 125)
        self.assertEqual(report["population"]["temporally_matched_candidate_provider_minutes"], 5)
        self.assertEqual(report["source_queries"], [{"product": q["product"],
            "collection_version": "2.1", "query_url": q["url"],
            "response_sha256": q["response_sha256"], "cmr_hits": q["cmr_hits"]}
            for q in snapshot["queries"]])
        self.assertFalse(report["observation_opportunity_verified"])


if __name__ == "__main__": unittest.main()
