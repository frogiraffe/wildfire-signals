import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fire_public import collect, pilot
from fire_public.pilot_window import state


class PilotTests(unittest.TestCase):
    def test_window_stops_after_end(self):
        start,end='2026-10-09T18:00:00Z','2026-10-16T18:00:00Z'
        self.assertEqual(state('2026-10-10T18:00:00Z',start,end),
                         {'active':'true','expired':'false'})
        self.assertEqual(state(end,start,end),{'active':'false','expired':'true'})

    def test_source_failure_recorded_without_secret_or_publication(self):
        at=datetime(2026,10,9,18,tzinfo=timezone.utc)
        with (patch.object(collect,'fetch_firms',side_effect=collect.SourceDeferred('quota')),
              patch.object(collect,'fetch_nifc',return_value=[]),
              patch.object(collect,'fetch_cwfis',return_value=[])):
            result=pilot.measure(at=at,key='private-key')
        self.assertFalse(result['publication_attempted'])
        self.assertEqual(result['sources']['VIIRS_NOAA20_NRT']['status'],'deferred')
        self.assertNotIn('private-key',str(result))


if __name__ == '__main__':
    unittest.main()
