import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fire_public import collect, pilot
from fire_public.pilot_window import state
from fire_public.pilot_audit import audit


class PilotTests(unittest.TestCase):
    def test_window_stops_after_end(self):
        start,end='2026-10-09T18:00:00Z','2026-10-16T18:00:00Z'
        self.assertEqual(state('2026-10-10T18:00:00Z',start,end),
                         {'active':'true','expired':'false'})
        self.assertEqual(state(end,start,end),{'active':'false','expired':'true'})

    def test_window_cannot_be_extended_beyond_seven_days(self):
        with self.assertRaises(ValueError):
            state('2026-10-10T18:00:00Z','2026-10-09T18:00:00Z',
                  '2026-10-17T18:00:00Z')

    def test_source_failure_recorded_without_secret_or_publication(self):
        at=datetime(2026,10,9,18,tzinfo=timezone.utc)
        with (patch.object(collect,'fetch_firms',side_effect=collect.SourceDeferred('quota')),
              patch.object(collect,'fetch_nifc',return_value=[]),
              patch.object(collect,'fetch_cwfis',return_value=[])):
            result=pilot.measure(at=at,key='private-key')
        self.assertFalse(result['publication_attempted'])
        self.assertEqual(result['sources']['VIIRS_NOAA20_NRT']['status'],'deferred')
        self.assertNotIn('private-key',str(result))

    def test_interval_ledger_separates_success_failure_and_missing(self):
        runs=[{'event':'schedule','createdAt':'2026-10-09T19:38:00Z',
               'status':'completed','conclusion':'success'},
              {'event':'schedule','createdAt':'2026-10-09T20:38:00Z',
               'status':'completed','conclusion':'failure'}]
        result=audit(runs,until='2026-10-09T22:37:00Z')
        self.assertEqual(result['expected_intervals'],4)
        self.assertEqual(result['successful_intervals'],1)
        self.assertEqual(len(result['failed_intervals']),1)
        self.assertEqual(len(result['missing_intervals']),2)


if __name__ == '__main__':
    unittest.main()
