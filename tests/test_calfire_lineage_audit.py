"""Source-hash replay and synthetic reviewer/document provenance regression tests.

No real independent human reviews or verified fire/nonfire labels are created.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from fire_public.calfire_ambiguity_dossiers import build_from_matrix
from fire_public.calfire_blind_review import _original_cases, packet, _write_new
from fire_public.calfire_lineage_audit import analyze, offline_html
from fire_public.mtbs_event_corroboration import capture, _archive
from fire_public.mtbs_match_review import load_study
from test_calfire_incident_matrix import FullDetailCoverageTests


class IndependentDocumentLineageTests(unittest.TestCase):
    def setUp(self):
        fixture = FullDetailCoverageTests("test_replay_full_source_url_partition_and_explicit_non_truth")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.root = fixture.root
        self.study, self.annual, self.batches = fixture.study, fixture.annual, fixture.batch_paths
        self.casebook = build_from_matrix(fixture.full())
        self.cases = _original_cases(self.casebook)
        self.study_meta, self.study_sha, source_cases = load_study(self.study)
        self.original = {c["candidate_id"]: c for c in source_cases}
        self.store = self.root / "private-archived-document-store"
        self.store.mkdir()
        self.target = next(iter(self.cases))

    def votes(self, who, mode="prefer_source_lead"):
        _, data = packet(self.casebook, who)
        for vote in data["votes"]:
            vote.update(reviewed_at="2026-10-13T17:00:00Z",
                        reason="Original document lineage not yet independently authenticated.")
            if mode == "prefer_source_lead":
                vote.update(decision=mode,
                            selected_source_url=self.cases[vote["candidate_id"]][
                                "official_calfire_page_options"][0]["source_url"],
                            external_evidence_url="https://example.org/research/" + who,
                            source_lineage="potentially_independent_not_verified")
        return data

    def receipt(self, who, *, publisher=None, upstream=None, duplicate_bytes=False,
                published="2026-10-13T12:00:00Z", captured="2026-10-13T13:00:00Z",
                event_day="2018-07-20T00:00:00Z", relation="same_event_document_claim"):
        case = self.original[self.target]
        source_url = "https://example.org/research/" + who
        meta = {
            "schema_version": 1,
            "candidate_id": self.target,
            "mtbs_fire_id": case["mtbs"]["fire_id"],
            "nifc_object_id": case["nifc"]["object_id"],
            "nifc_source_identity": case["nifc"]["source_identity"],
            "source_url": source_url,
            "rights_url": "https://example.org/license",
            "publisher_id": publisher or "original-publisher-" + who,
            "upstream_family": upstream or "agency-incident-family-" + who,
            "source_record_id": "original-archive-" + who,
            "source_kind": "historical source artifact",
            "upstream_role": "firsthand_original_record",
            "relation_claim": relation,
            "source_published_at": published,
            "source_event_at": event_day,
            "researcher_note": "SYNTHETIC test record; the remote publisher is not verified.",
        }
        meta_path = self.root / ("source-" + who + ".json")
        doc_path = self.root / ("source-" + who + ".bin")
        meta_path.write_text(json.dumps(meta))
        doc_path.write_bytes(b"synthetic original evidence " +
                             (b"identical" if duplicate_bytes else who.encode()))
        return capture(self.study, self.store, meta_path, doc_path, captured_at=captured)

    def loaded(self):
        return _archive(self.store, self.study_sha, self.original)

    def test_missing_reviews_and_archive_never_become_truth(self):
        result = analyze(self.casebook)
        self.assertEqual(result["original_candidate_population"],
                         self.casebook["research_candidate_count"])
        self.assertEqual(result["ambiguous_cases_audited"], len(self.cases))
        self.assertEqual(result["statuses"]["awaiting_independent_human_reviews"], len(self.cases))
        self.assertEqual(result["verified_same_event_crosswalks"], 0)
        self.assertEqual(result["verified_nonfire_labels"], 0)
        self.assertFalse(result["forecast_skill_measured"])
        self.assertEqual(result["evidence_graph"]["independent_upstream_origins_authenticated"], 0)
        for row in result["cases"]:
            self.assertIn("two_completed_blind_reviews_missing", row["unresolved_gates"])
            self.assertFalse(row["independent_source_lineage_proven"])
            self.assertFalse(row["verified_fire_presence_or_absence"])
        self.assertTrue(any(n["kind"] == "calfire_original_page"
                            for n in result["evidence_graph"]["nodes"]))
        self.assertTrue(all(not e["physical_event_identity_proven"]
                            for e in result["evidence_graph"]["edges"]))

    def test_two_original_documents_are_structurally_reviewable_not_identity(self):
        first, second = self.votes("alice"), self.votes("bob")
        # Other candidate cases have no supporting private receipts.
        self.receipt("alice")
        self.receipt("bob")
        result = analyze(self.casebook, first, second, self.loaded())
        row = next(x for x in result["cases"] if x["candidate_id"] == self.target)
        self.assertEqual(row["status"], "structurally_reviewable_not_authenticated")
        self.assertEqual(row["unresolved_gates"], [])
        self.assertEqual(row["private_documents_archived"], 2)
        self.assertEqual(len(row["cited_document_links"]), 2)
        self.assertEqual(result["statuses"]["structurally_reviewable_not_authenticated"], 1)
        self.assertEqual(result["statuses"]["source_lineage_or_citation_gaps"],
                         len(self.cases) - 1)
        self.assertEqual(result["private_receipts_verified"], 2)
        self.assertEqual(result["verified_same_event_crosswalks"], 0)
        self.assertTrue(all(not n["independent_origin_verified"]
                            for n in result["evidence_graph"]["nodes"]))
        self.assertEqual(result, analyze(self.casebook, first, second, self.loaded()))

    def test_same_bytes_same_lineage_and_after_review_capture_are_flagged(self):
        first, second = self.votes("alice"), self.votes("bob")
        self.receipt("alice", publisher="shared-publisher", upstream="same-family",
                     duplicate_bytes=True)
        self.receipt("bob", publisher="shared-publisher", upstream="same-family",
                     duplicate_bytes=True, captured="2026-10-13T20:00:00Z")
        result = analyze(self.casebook, first, second, self.loaded())
        row = next(x for x in result["cases"] if x["candidate_id"] == self.target)
        self.assertEqual(row["status"], "source_lineage_or_citation_gaps")
        self.assertIn("identical_document_bytes_reused_as_two_sources", row["unresolved_gates"])
        self.assertIn("distinct_declared_publishers_missing", row["unresolved_gates"])
        self.assertIn("distinct_declared_upstream_families_missing", row["unresolved_gates"])
        self.assertIn("evidence_document_archived_after_reviewer_vote", row["unresolved_gates"])

    def test_conflict_and_shared_citation_across_candidates_retained(self):
        first, second = self.votes("alice"), self.votes("bob")
        for vote in second["votes"]:
            if vote["candidate_id"] == self.target:
                vote["selected_source_url"] = self.cases[self.target][
                    "official_calfire_page_options"][-1]["source_url"]
        result = analyze(self.casebook, first, second)
        row = next(x for x in result["cases"] if x["candidate_id"] == self.target)
        self.assertEqual(row["status"], "unresolved_human_hypotheses")
        self.assertIsNone(row["review_hypothesis"])
        self.assertIn("review_citation_reused_across_candidate_pairs", row["unresolved_gates"])
        self.assertEqual(result["verified_same_event_crosswalks"], 0)

    def test_missing_or_mismatched_receipt_rejected_and_label_forgery_cannot_render(self):
        with self.assertRaisesRegex(ValueError, "pair"):
            analyze(self.casebook, self.votes("alice"), None)
        bad = copy.deepcopy(self.casebook)
        bad["verified_event_crosswalks"] = 8
        # Original source replayer, not this derived value, is authoritative.
        bad["validated_same_fire_event_crosswalks"] = 3
        with self.assertRaisesRegex(ValueError, "unverified original-source"):
            analyze(bad)
        self.receipt("alice")
        receipts = self.loaded()
        receipts[0]["source_study_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "boundaries"):
            analyze(self.casebook, receipts=receipts)
        rendered = offline_html(analyze(self.casebook))
        self.assertIn("script-src &#x27;none&#x27;", rendered)
        self.assertNotIn("<script", rendered)
        fake = dict(analyze(self.casebook), verified_nonfire_labels=1)
        with self.assertRaisesRegex(ValueError, "fabricated"):
            offline_html(fake)

    def test_tampered_original_document_bytes_fail_closed(self):
        receipt = self.receipt("alice")
        doc = self.store / "event-corroboration/blobs" / (receipt["document_sha256"] + ".bin")
        doc.write_bytes(b"tampered source content")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.loaded()

    def test_cli_replays_original_sources_and_writes_private_no_network_outputs(self):
        target = self.root / "private-lineage"
        argv = [sys.executable, "-m", "fire_public.calfire_lineage_audit",
                "--study-dir", str(self.study),
                "--calfire-archive-dir", str(self.annual),
                "--output-dir", str(target)]
        for batch in self.batches:
            argv.extend(["--batch", str(batch)])
        result = subprocess.run(argv, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        obj = json.loads((target / "private-lineage-audit.json").read_text())
        self.assertEqual(obj["ambiguous_cases_audited"], len(self.cases))
        self.assertEqual(obj["verified_same_event_crosswalks"], 0)
        self.assertTrue((target / "private-lineage-audit.html").is_file())
        self.assertEqual((target / "private-lineage-audit.json").stat().st_mode & 0o777, 0o600)
        self.assertNotEqual(subprocess.run(argv, capture_output=True).returncode, 0)
        data = next(self.study.glob("nifc-*-page-*.geojson"))
        data.write_bytes(data.read_bytes() + b" ")
        argv[argv.index("--output-dir") + 1] = str(self.root / "tamper-output")
        self.assertNotEqual(subprocess.run(argv, capture_output=True).returncode, 0)
        self.assertFalse((self.root / "tamper-output").exists())


if __name__ == "__main__":
    unittest.main()
