"""Synthetic reviewer scenarios against SHA-replayed CAL FIRE matrix fixtures."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from fire_public.calfire_ambiguity_dossiers import build_from_matrix
from fire_public.calfire_blind_review import (
    _digest, _original_cases, _write_new, packet, reconcile,
)
from test_calfire_incident_matrix import FullDetailCoverageTests


class BlindAlternativeReviewTests(unittest.TestCase):
    def setUp(self):
        fixture = FullDetailCoverageTests("test_replay_full_source_url_partition_and_explicit_non_truth")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root = fixture.root
        self.study, self.annual, self.batches = fixture.study, fixture.annual, fixture.batch_paths
        self.report = build_from_matrix(fixture.full())
        self.cases = _original_cases(self.report)
        self.assertGreater(len(self.cases), 0)

    def votes(self, reviewer="reviewer-a", status="unresolved"):
        _, result = packet(self.report, reviewer)
        for vote in result["votes"]:
            vote["reviewed_at"] = "2026-10-13T00:00:00Z"
            vote["reason"] = "Independent evidence does not yet establish physical identity."
            if status == "prefer_source_lead":
                cid = vote["candidate_id"]
                vote["decision"] = status
                vote["selected_source_url"] = self.cases[cid]["official_calfire_page_options"][0]["source_url"]
                vote["external_evidence_url"] = "https://example.org/reviewer-note"
                vote["source_lineage"] = "unknown"
        return result

    def test_review_packet_is_blind_escaped_bound_and_label_free(self):
        html, vote = packet(self.report, "<reviewer>")
        self.assertIn("&lt;reviewer&gt;", html)
        self.assertIn("script-src &#x27;none&#x27;", html)
        self.assertNotIn("<script", html)
        self.assertEqual(vote["casebook_sha256"], _digest(self.report))
        self.assertEqual(len(vote["votes"]), len(self.cases))
        self.assertTrue(all(v["selected_source_url"] is None for v in vote["votes"]))
        self.assertNotIn("verified_same_fire_event_crosswalks", vote)
        self.assertTrue(all(len(c["official_calfire_page_options"]) > 1
                            for c in self.cases.values()))

    def test_distinct_reviewers_agree_only_on_unverified_hypotheses(self):
        first, second = self.votes("alice", "prefer_source_lead"), self.votes("bob", "prefer_source_lead")
        result = reconcile(self.report, first, second)
        self.assertEqual(result["dispositions"]["concordant_unverified_lead"], len(self.cases))
        self.assertEqual(result["verified_same_fire_event_crosswalks"], 0)
        self.assertEqual(result["verified_nonfire_labels"], 0)
        self.assertFalse(result["forecast_skill_measured"])
        self.assertEqual(result["original_nifc_mtbs_study_sha256"],
                         self.report["nifc_mtbs_original_study_sha256"])
        for row in result["cases"]:
            self.assertFalse(row["same_physical_fire_verified"])
            self.assertFalse(row["verified_nonfire"])
            self.assertIn("source_independence_not_authenticated", row["research_flags"])
            self.assertIn("same_evidence_url_not_independent_corroboration", row["research_flags"])
            self.assertIsNotNone(row["agreed_lead_hypothesis"])
        self.assertEqual(result, reconcile(self.report, first, second))

    def test_conflicting_alternative_urls_and_abstentions_survive(self):
        first, second = self.votes("alice", "prefer_source_lead"), self.votes("bob", "prefer_source_lead")
        first_case = next(iter(self.cases))
        choices = self.cases[first_case]["official_calfire_page_options"]
        for vote in second["votes"]:
            if vote["candidate_id"] == first_case:
                vote["selected_source_url"] = choices[-1]["source_url"]
        result = reconcile(self.report, first, second)
        conflict = next(r for r in result["cases"] if r["candidate_id"] == first_case)
        self.assertEqual(conflict["status"], "conflicting_source_leads")
        self.assertIsNone(conflict["agreed_lead_hypothesis"])
        self.assertNotEqual(conflict["first"]["selected_source_url"],
                            conflict["second"]["selected_source_url"])
        self.assertIn("unresolved_or_conflicting_independent_review", conflict["research_flags"])

        abstained = self.votes("bob", "unresolved")
        result = reconcile(self.report, first, abstained)
        self.assertEqual(result["dispositions"]["partially_unresolved"], len(self.cases))
        self.assertTrue(all(r["agreed_lead_hypothesis"] is None for r in result["cases"]))

    def test_every_vote_must_belong_to_complete_fixed_source_population(self):
        first = self.votes("alice", "prefer_source_lead")
        second = self.votes("bob", "prefer_source_lead")
        bad = copy.deepcopy(first)
        bad["casebook_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "exact original-source casebook"):
            reconcile(self.report, bad, second)
        bad = copy.deepcopy(first)
        bad["votes"].pop()
        with self.assertRaisesRegex(ValueError, "every ambiguous case"):
            reconcile(self.report, bad, second)
        bad = copy.deepcopy(first)
        bad["votes"][0]["candidate_id"] = "not-an-existing-case"
        with self.assertRaisesRegex(ValueError, "unknown or duplicate"):
            reconcile(self.report, bad, second)
        with self.assertRaisesRegex(ValueError, "distinct reviewer"):
            reconcile(self.report, first, copy.deepcopy(first))

    def test_nonexistent_leads_and_unproven_claims_fail_closed(self):
        first, second = self.votes("alice", "prefer_source_lead"), self.votes("bob")
        for key, value, message in [
            ("selected_source_url", "https://example.org/fake", "original official URL"),
            ("external_evidence_url", "javascript:alert(1)", "HTTPS evidence"),
            ("decision", "same_fire_confirmed", "research decision"),
            ("source_lineage", "independent_verified", "research decision"),
            ("reviewed_at", "2018-05-01", "UTC offset"),
        ]:
            bad = copy.deepcopy(first)
            bad["votes"][0][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, message):
                reconcile(self.report, bad, second)
        bad = copy.deepcopy(second)
        bad["votes"][0]["selected_source_url"] = "https://example.org/fake"
        with self.assertRaisesRegex(ValueError, "unresolved vote"):
            reconcile(self.report, bad, first)

    def test_derived_dossier_metadata_tamper_is_not_accepted(self):
        for patch in [
            {"validated_same_fire_event_crosswalks": 1},
            {"independent_nonfire_observations": 1},
            {"measured_wildfire_forecast_skill": True},
            {"candidate_linked_unique_pages_verified": -1},
        ]:
            with self.subTest(patch=patch):
                with self.assertRaises(ValueError):
                    packet(dict(self.report, **patch), "alice")
        malformed = copy.deepcopy(self.report)
        one = next(c for c in malformed["cases"] if c["source_option_count"] > 1)
        one["official_calfire_page_options"][0]["verified_event_identity"] = True
        with self.assertRaisesRegex(ValueError, "unverified source page"):
            packet(malformed, "alice")

    def test_private_new_only_outputs_and_original_input_protection(self):
        folder = self.root / "private-independent"
        _, votes = packet(self.report, "alice")
        _write_new(folder, {"votes.json": (json.dumps(votes) + "\n").encode()},
                   [self.study, self.annual, *self.batches])
        self.assertEqual(json.loads((folder / "votes.json").read_text()), votes)
        self.assertEqual((folder / "votes.json").stat().st_mode & 0o777, 0o600)
        with self.assertRaisesRegex(ValueError, "new private output"):
            _write_new(folder, {"oops.json": b"{}"}, [self.study])
        with self.assertRaisesRegex(ValueError, "overlap"):
            _write_new(self.study / "private", {"oops.json": b"{}"}, [self.study])

    def test_cli_replays_all_original_evidence_and_detects_source_tamper(self):
        out = self.root / "blind-packet-cli"
        cmd = [sys.executable, "-m", "fire_public.calfire_blind_review",
               "packet", "--study-dir", str(self.study),
               "--calfire-archive-dir", str(self.annual),
               "--reviewer-id", "independent-test-fixture",
               "--output-dir", str(out)]
        for batch in self.batches:
            cmd.extend(["--batch", str(batch)])
        run = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue((out / "independent-packet.html").is_file())
        self.assertEqual(len(json.loads((out / "private-vote-template.json").read_text())["votes"]),
                         len(self.cases))
        self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
        original = next(self.study.glob("nifc-*-page-*.geojson"))
        original.write_bytes(original.read_bytes() + b" ")
        changed = cmd[:]
        changed[changed.index("--output-dir") + 1] = str(self.root / "tampered")
        self.assertNotEqual(subprocess.run(changed, capture_output=True).returncode, 0)
        self.assertFalse((self.root / "tampered").exists())


if __name__ == "__main__":
    unittest.main()
