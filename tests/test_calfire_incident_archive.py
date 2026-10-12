"""Original HTML archival contract with actual NIFC/MTBS source-shaped fixtures.

The CAL FIRE HTML and NIFC/MTBS records in these tests are synthetic.
A separate live GitHub Actions job fetches www.fire.ca.gov itself.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

from fire_public.calfire_incident_archive import (
    SOURCE, compare, parse_archive, replay, save, _incident_path,
)
from test_mtbs_match_review import PairReviewTests


def html_archive(*,change=None):
    rows=[]
    for i in range(1,15):
        name=(f"Fire record {i}" if i<=4 else f"Unrelated report {i}")
        if change=="same-names" and i==2:
            name="Fire record 1"
        start="7/20/2018" if i!=14 else "12/31/1969"
        url=f"/incidents/2018/7/20/example-{i}"
        if change=="outside-url" and i==1:
            url="https://evil.example/incidents/2018/7/20/fake"
        rows.append(
            "<tr><td><a href='"+url+"'>"+name+"</a></td>"
            "<td>Shasta</td><td>"+start+"</td><td>1,300</td><td>100%</td></tr>"
        )
    return (
        "<!doctype html><html><head><title>2018 Incidents</title></head>"
        "<body><h1>2018 Fire Season</h1><table>"
        "<thead><tr><th>Incident</th><th>Counties</th><th>Started</th>"
        "<th>Acres</th><th>Containment</th></tr></thead>"
        "<tbody>"+"".join(rows)+"</tbody></table></body></html>"
    ).encode()


class OriginalCALFIRECrosswalkTests(unittest.TestCase):
    def setUp(self):
        obj=PairReviewTests("test_source_verified_packet_and_original_identity")
        obj.setUp()
        self.addCleanup(obj.doCleanups)
        self.fixture=obj
        self.root=obj.root
        self.study=obj.study
        self.original=html_archive()

    def test_original_table_parser_keeps_ids_dates_and_explicit_old_date_flag(self):
        rows=parse_archive(self.original)
        self.assertEqual(len(rows),14)
        self.assertEqual(rows[0]["source_started_at"],"2018-07-20")
        self.assertEqual(rows[0]["reported_acres"],1300)
        self.assertEqual(rows[0]["counties"],"Shasta")
        self.assertEqual(rows[0]["original_event_url"],
                         "https://www.fire.ca.gov/incidents/2018/7/20/example-1")
        self.assertFalse(rows[0]["independently_authenticated_event_identity"])
        self.assertFalse(rows[-1]["started_year_is_requested_2018"])
        self.assertEqual(rows[-1]["source_started_at"],"1969-12-31")

    def test_real_provider_shaped_case_pairs_get_only_ambiguous_name_leads(self):
        result=compare(self.study,self.original,captured_at="2026-10-13T15:00:00Z")
        self.assertEqual(result["case_count"],len(self.fixture.report["candidate_pairs"]))
        self.assertEqual(result["calfire_archive_records_parsed"],14)
        self.assertEqual(result["archive_records_with_non2018_or_unknown_dates"],1)
        self.assertEqual(result["confirmed_event_identity_count"],0)
        self.assertEqual(result["verified_nonfire_labels"],0)
        self.assertFalse(result["calibrated_model_accuracy_measured"])
        self.assertTrue(result["source_upstream_independence_from_nifc_or_mtbs_unverified"])
        self.assertEqual(result["source_original_html_sha256"],hashlib.sha256(
            self.original).hexdigest())
        self.assertTrue(any(x["evidence_lead_status"]=="exact_normalized_source_name"
                            for x in result["cases"]))
        self.assertTrue(all(not x["candidate_fire_event_identity_verified"]
                            for x in result["cases"]))
        self.assertTrue(all(x["missing_calfire_name_lead_is_not_nonfire"]
                            for x in result["cases"]))
        self.assertTrue(all(not lead["same_fire_event_verified"]
                            for x in result["cases"]
                            for lead in x["calfire_name_only_leads"]))

    def test_same_name_multiple_official_archive_rows_stay_multiple_leads(self):
        result=compare(self.study,html_archive(change="same-names"),
                       captured_at="2026-10-13T15:00:00Z")
        self.assertTrue(any(len(x["calfire_name_only_leads"])>=2
                            for x in result["cases"]))
        self.assertEqual(result["confirmed_event_identity_count"],0)

    def test_bad_source_archive_title_and_untrusted_link_are_rejected(self):
        with self.assertRaisesRegex(ValueError,"2018 incident archive"):
            parse_archive(self.original.replace(b"2018 Incidents",b"2017 Incidents")
                          .replace(b"2018 Fire Season",b"2017 Fire Season"))
        with self.assertRaisesRegex(ValueError,"unique official event page"):
            parse_archive(html_archive(change="outside-url"))
        self.assertIsNone(_incident_path("http://www.fire.ca.gov/incidents/2018/hi"))
        self.assertIsNone(_incident_path("https://evil.example/incidents/2018/hi"))
        self.assertEqual(_incident_path("/incidents/2018/7/20/example-1"),
                         "https://www.fire.ca.gov/incidents/2018/7/20/example-1")

    def test_different_year_or_empty_archive_cannot_be_negative(self):
        with self.assertRaisesRegex(ValueError,"plausible 2018 incident"):
            parse_archive(b"<h1>2018 Incidents</h1><table>"
                          b"<tr><th>Incident</th><th>Counties</th><th>Started</th>"
                          b"<th>Acres</th><th>Containment</th></tr></table>")

    def test_all_source_bytes_export_immutable_and_offline_replay(self):
        data=compare(self.study,self.original,captured_at="2026-10-13T15:00:00Z")
        out=self.root/"original-calfire-capture"
        save(out,self.original,data)
        self.assertEqual((out/"original-calfire-2018.html").read_bytes(),self.original)
        self.assertEqual(replay(self.study,out),data)
        with self.assertRaisesRegex(ValueError,"new original source archive"):
            save(out,self.original,data)
        doc=out/"original-calfire-2018.html"
        doc.write_bytes(doc.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError,"original source bytes are corrupted"):
            replay(self.study,out)

    def test_edited_derived_report_detected_against_original_html(self):
        data=compare(self.study,self.original,captured_at="2026-10-13T15:00:00Z")
        out=self.root/"archive"
        save(out,self.original,data)
        file=out/"original-calfire-cross-reference.json"
        model=json.loads(file.read_text())
        model["cases"][0]["calfire_name_only_leads"]=[]
        file.write_text(json.dumps(model))
        with self.assertRaisesRegex(ValueError,"archive report changed"):
            replay(self.study,out)

    def test_original_nifc_record_corruption_stops_third_source_analysis(self):
        file=next(self.study.glob("nifc-*-page-*.geojson"))
        file.write_bytes(file.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError,"SHA-256"):
            compare(self.study,self.original,captured_at="2026-10-13T15:00:00Z")

    def test_source_capture_has_aware_timestamp_and_no_remote_production(self):
        with self.assertRaisesRegex(ValueError,"UTC offset aware"):
            compare(self.study,self.original,captured_at="2026-10-13T15:00:00")
        with self.assertRaisesRegex(ValueError,"pinned CAL FIRE archive"):
            other=self.root/"fake-report"
            # Contract is 2018-only; schema-year protection enforced in module.
            with patch("fire_public.calfire_incident_archive.load_study",
                 return_value=({"year":2017}, "0"*64, [])):
                compare(other,self.original,captured_at="2026-10-13T15:00:00Z")


if __name__=="__main__":
    unittest.main()
