import gzip
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fire_public.collect import parse_firms_csv
from fire_public.pixel_archive import PixelArchive, write_scan_receipt
from fire_public.cli import fetch_firms_with_archive, should_archive_analysis

AT = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
CSV = ("latitude,longitude,acq_date,acq_time,frp,confidence,bright_ti4,scan,track,daynight\n"
       "36.900,30.700,2026-10-12,1130,5.5,n,330.1,0.38,0.42,D\n"
       "36.901,30.701,2026-10-12,1135,7.0,h,341.0,0.39,0.41,N\n"
       "91,30.7,2026-10-12,1136,8,h,340,0.4,0.4,D\n")


class FirmsPixelTests(unittest.TestCase):
    def test_archive_keeps_individual_frp_quality_and_rejected_rows_out(self):
        with tempfile.TemporaryDirectory() as temp:
            with PixelArchive(Path(temp), at=AT) as archive:
                events = parse_firms_csv(CSV, "VIIRS_NOAA20_NRT", at=AT,
                                         pixel_sink=archive.append)
            self.assertEqual(events[0]["detection_count"], 2)
            paths = list(Path(temp).glob('firms-pixels-*.jsonl.gz'))
            self.assertEqual(len(paths), 1)
            with gzip.open(paths[0], 'rt') as source:
                rows = [json.loads(line) for line in source]
            self.assertEqual(len(rows), 2)
            self.assertEqual([row["frp_mw"] for row in rows], [5.5, 7.0])
            self.assertEqual([row["confidence"] for row in rows], ['n','h'])
            self.assertEqual(rows[0]["candidate_id"], events[0]["event_id"])
            self.assertEqual(rows[0]["resolution_km"], [0.38,0.42])
            self.assertEqual(rows[0]["observed_at"], '2026-10-12T11:30:00+00:00')
            self.assertEqual(rows[0]["received_at"], AT.isoformat())
            self.assertEqual(len(rows[0]["content_sha256"]),64)
            self.assertEqual(rows[0]["source_fields"]["frp"],"5.5")
            self.assertNotIn('MAP_KEY', json.dumps(rows))

    def test_invalid_frp_is_unknown_not_zero(self):
        rows=[]
        parse_firms_csv(CSV.replace('5.5,n','bad,n'), 'VIIRS_NOAA20_NRT',at=AT,
                        pixel_sink=rows.append)
        self.assertIsNone(rows[0]['frp_mw'])

    def test_failed_scan_does_not_publish_partial_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError,'failure'):
                with PixelArchive(Path(temp),at=AT) as archive:
                    archive.append({'source':'test'})
                    raise RuntimeError('failure')
            self.assertEqual(list(Path(temp).iterdir()),[])

    def test_collector_archives_pixels_when_analysis_archive_is_enabled(self):
        with tempfile.TemporaryDirectory() as temp:
            def download(key, source, *, at, pixel_sink):
                return parse_firms_csv(CSV,source,at=at,pixel_sink=pixel_sink)
            with patch('fire_public.cli.fetch_firms',side_effect=download):
                events = fetch_firms_with_archive('secret-key','VIIRS_NOAA20_NRT',
                                                  at=AT,directory=Path(temp))
            self.assertEqual(events[0]['detection_count'],2)
            self.assertEqual(len(list(Path(temp).glob('firms-pixels-*.jsonl.gz'))),1)

    def test_collector_discards_partial_source_file_on_error(self):
        with tempfile.TemporaryDirectory() as temp:
            def download(key, source, *, at, pixel_sink):
                pixel_sink({'source':source})
                raise ValueError('bad upstream')
            with patch('fire_public.cli.fetch_firms',side_effect=download):
                with self.assertRaisesRegex(ValueError,'bad upstream'):
                    fetch_firms_with_archive('secret-key','VIIRS_NOAA20_NRT',
                                             at=AT,directory=Path(temp))
            self.assertEqual(list(Path(temp).iterdir()),[])

    def test_archive_uses_four_daily_windows_and_skips_manual_repair(self):
        scheduled=AT.replace(minute=17)
        self.assertTrue(should_archive_analysis(scheduled,enabled=True,forced=False))
        self.assertFalse(should_archive_analysis(scheduled.replace(hour=13),enabled=True,forced=False))
        self.assertFalse(should_archive_analysis(scheduled,enabled=False,forced=False))
        self.assertFalse(should_archive_analysis(scheduled,enabled=True,forced=True))

    def test_scan_receipt_records_empty_and_failed_sources(self):
        snapshot={'manifest':{'last_scan_at':AT.isoformat(),'data_status':'partial'},
                  'sources':[{'key':'VIIRS_NOAA20_NRT','status':'complete'},
                             {'key':'VIIRS_NOAA21_NRT','status':'failed'}]}
        with tempfile.TemporaryDirectory() as temp:
            path=write_scan_receipt(snapshot,Path(temp),'snapshot:'+'a'*64)
            with gzip.open(path,'rt') as source:
                receipt=json.load(source)
            self.assertEqual(receipt['source_states']['VIIRS_NOAA20_NRT'],'complete')
            self.assertEqual(receipt['source_states']['VIIRS_NOAA21_NRT'],'failed')
            self.assertEqual(receipt['pixel_files'],[])


if __name__ == '__main__':
    unittest.main()
