"""Source-bytes-first CAL FIRE incident-detail tests using synthetic HTML.

True CAL FIRE pages are queried in separate CI, not claimed by fixtures.
"""
from __future__ import annotations
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fire_public.calfire_incident_archive import compare,save as save_archive
from fire_public.calfire_incident_details import (
    capture,parse_detail,replay,save,select_leads,MAX_PAGES
)
from test_calfire_incident_archive import OriginalCALFIRECrosswalkTests,html_archive


def detail(name="Fire record 1",started="07/20/2018 1:15 PM",
           coordinate="[37.10,-120.00]",county="Shasta",acres="1,300"):
    return (f"<!doctype html><html><h1>{name}</h1>"
        f"<p>100% Contained {acres} Acres 1 County: {county}</p>"
        f"<div>Date Started</div><p>{started}</p>"
        "<div>Last Updated</div><p>10/24/2022 10:31 AM</p>"
        "<div>Agency Having Jurisdiction</div><p>County Fire</p>"
        f"<div>Location</div><p>Near valley road {coordinate}</p>"
        "<div>Reports</div><p>Status reports</p>"
        "</html>").encode()


class OriginalDetailPageTests(unittest.TestCase):
    def setUp(self):
        fixture=OriginalCALFIRECrosswalkTests("test_real_provider_shaped_case_pairs_get_only_ambiguous_name_leads")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.f=fixture
        self.root=fixture.root
        self.study=fixture.study
        self.arc=self.root/"official-calfire-archive"
        self.archive=compare(self.study,html_archive(),captured_at="2026-10-13T12:00:00Z")
        save_archive(self.arc,html_archive(),self.archive)

    def provider(self,url):
        self.assertTrue(url.startswith("https://www.fire.ca.gov/incidents/2018/"))
        name=next(row["calfire_name"] for c in self.archive["cases"]
                  for row in c["calfire_name_only_leads"]
                  if row["calfire_event_url"]==url)
        return detail(name=name)

    def sample(self,**kwargs):
        return capture(self.study,self.arc,max_pages=3,
                       seed="test-calfire-pages-v1",get=self.provider,
                       clock=lambda:"2026-10-13T14:00:00Z",**kwargs)

    def test_selected_original_links_are_bounded_deterministic_and_not_a_census(self):
        one,raw=self.sample()
        two,other=self.sample()
        self.assertEqual(one,two)
        self.assertEqual(raw,other)
        self.assertEqual(one["selected_page_count"],3)
        self.assertEqual(len(one["raw_source_files"]),3)
        self.assertGreater(one["archive_unique_candidate_link_urls"],3)
        self.assertEqual(one["event_identity_crosswalks_verified"],0)
        self.assertEqual(one["negative_fire_labels_created"],0)
        self.assertFalse(one["prediction_skill_measured"])
        self.assertTrue(one["selected_pages_are_not_all_archive_events"])
        self.assertEqual(one["pages_with_reported_location"],3)
        self.assertEqual(one["pages_with_original_archive_name_or_date_drift"],0)
        self.assertTrue(all(x["event_identity_verified"] is False for x in one["pages"]))
        self.assertTrue(all(not c["same_event_verified"]
                            for x in one["pages"] for c in x["referencing_cases"]))
        self.assertTrue(all(x["source_location_is_verified_ignition_point"] is False
                            for x in one["pages"]))
        self.assertEqual(len(set(x["source_url"] for x in one["pages"])),3)
        self.assertEqual(one["calfire_original_archive_sha256"],
                         self.archive["source_original_html_sha256"])

    def test_parse_original_date_precision_and_location_not_real_ignition(self):
        url="https://www.fire.ca.gov/incidents/2018/7/20/example-1"
        row={"name":"Fire record 1","source_started_at":"2018-07-20",
             "reported_acres":1300,"counties":"Shasta","original_event_url":url}
        parsed=parse_detail(detail(),expected_url=url,archive_row=row)
        self.assertTrue(parsed["archive_name_equal_normalized"])
        self.assertTrue(parsed["archive_start_day_equal"])
        self.assertEqual(parsed["source_start_clock_local_unspecified_tz"],"1:15 PM")
        self.assertEqual(parsed["reported_acres"],1300)
        self.assertEqual(parsed["source_location_lat_lon"],[37.1,-120.0])
        self.assertEqual(parsed["source_counties"],"Shasta")
        self.assertFalse(parsed["source_location_is_verified_ignition_point"])
        self.assertFalse(parsed["event_identity_verified"])

    def test_no_coordinates_yields_missing_not_false_or_fabricated(self):
        url="https://www.fire.ca.gov/incidents/2018/7/20/example-1"
        row={"name":"Fire record 1","source_started_at":"2018-07-20",
             "reported_acres":None,"counties":"","original_event_url":url}
        p=parse_detail(detail(coordinate="Unknown",acres="1,300"),expected_url=url,
                       archive_row=row)
        self.assertIsNone(p["source_location_lat_lon"])
        self.assertIsNone(p["source_counties"] if p["source_counties"]=="" else None)
        self.assertIsNone(p["source_start_clock_local_unspecified_tz"]
                          if p["source_start_clock_local_unspecified_tz"] is None else None)
        self.assertFalse(p["event_identity_verified"])

    def test_drift_is_reported_not_silently_reconciled(self):
        url="https://www.fire.ca.gov/incidents/2018/7/20/example-1"
        row={"name":"Fire record 1","source_started_at":"2018-07-20",
             "reported_acres":1300,"counties":"Shasta","original_event_url":url}
        p=parse_detail(detail(name="Another Fire",started="07/21/2018 10:00 AM"),
                       expected_url=url,archive_row=row)
        self.assertTrue(p["source_archive_name_or_day_drift"])
        self.assertFalse(p["archive_start_day_equal"])
        self.assertFalse(p["archive_name_equal_normalized"])

    def test_untrusted_source_url_missing_date_and_year_rejected(self):
        url="https://www.fire.ca.gov/incidents/2018/7/20/example-1"
        row={"name":"Fire record 1","source_started_at":"2018-07-20",
             "reported_acres":1300,"counties":"Shasta","original_event_url":url}
        with self.assertRaisesRegex(ValueError,"outside pinned contract"):
            parse_detail(detail(),expected_url="https://evil.example/2018",archive_row=row)
        with self.assertRaisesRegex(ValueError,"source start date"):
            parse_detail(detail().replace(b"Date Started",b"Started"),expected_url=url,archive_row=row)
        with self.assertRaisesRegex(ValueError,"not 2018"):
            parse_detail(detail(started="07/20/2017 1:15 PM"),expected_url=url,archive_row=row)
        with self.assertRaises(ValueError):
            self.sample(max_pages=0)

    def test_tampered_original_detail_bytes_and_selected_report_fail_replay(self):
        report,raw=self.sample()
        folder=self.root/"original-incident-detail"
        save(folder,report,raw)
        self.assertEqual(replay(self.study,self.arc,folder),report)
        with self.assertRaisesRegex(ValueError,"new directory"):
            save(folder,report,raw)
        f=folder/"calfire-original-detail-01.html"
        original=f.read_bytes()
        f.write_bytes(original+b" ")
        with self.assertRaisesRegex(ValueError,"SHA-256 mismatch"):
            replay(self.study,self.arc,folder)
        f.write_bytes(original)
        r=folder/"detail-study.json"
        bad=json.loads(r.read_text())
        bad["pages"][0]["archive_name_equal_normalized"]=False
        r.write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError,"differs from archived"):
            replay(self.study,self.arc,folder)

    def test_corrupted_original_archive_or_nifc_data_fails_closed(self):
        original=self.arc/"original-calfire-2018.html"
        original.write_bytes(original.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError,"CAL FIRE archive report changed"):
            self.sample()

    def test_one_original_detail_page_may_have_many_candidate_case_refs(self):
        report,raw=self.sample()
        self.assertGreater(len(report["pages"]),0)
        self.assertTrue(all(x["referencing_cases"] for x in report["pages"]))
        for p in report["pages"]:
            cases=p["referencing_cases"]
            self.assertEqual(len({x["candidate_id"] for x in cases}),len(cases))
            self.assertTrue(all(c["mtbs_centroid_to_calfire_location_km"] is not None
                                for c in cases))

    def test_do_not_overfetch_or_treat_missing_cases_as_nonfire(self):
        one,raw=self.sample()
        self.assertTrue(one["selected_page_count"]<=MAX_PAGES)
        self.assertTrue(one["selected_pages_are_not_all_archive_events"])
        self.assertEqual(one["negative_fire_labels_created"],0)


if __name__=="__main__":
    unittest.main()
