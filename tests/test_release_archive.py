import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fire_public.release_archive import publish_daily_release


class ReleaseArchiveTests(unittest.TestCase):
    def test_daily_release_uploads_scan_assets_then_publishes(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            pixel=directory/'firms-pixels-20261012T181700Z-abc.jsonl.gz'
            pixel.write_bytes(gzip.compress(b'{"kind":"thermal_detection"}\n',mtime=0))
            scan={'schema_version':1,'role':'firms_pixel_scan_receipt',
                  'scan_at':'2026-10-12T18:17:00+00:00',
                  'pixel_files':[{'name':pixel.name,'sha256':hashlib.sha256(pixel.read_bytes()).hexdigest()}],
                  'source_states':{'VIIRS_NOAA20_NRT':'complete','VIIRS_NOAA21_NRT':'failed'}}
            (directory/'firms-pixel-scan-test.json.gz').write_bytes(
                gzip.compress(json.dumps(scan).encode(),mtime=0))
            calls=[]
            def api(method,url,data=None,content_type=None):
                calls.append((method,url,data))
                if method=='GET': return None
                if method=='POST' and url.endswith('/releases'): return {'id':7,'draft':True,'upload_url':'https://uploads.github.com/repos/frogiraffe/wildfire-signals/releases/7/assets{?name,label}'}
                if method=='POST': return {'name':url.split('name=')[1],
                                            'digest':'sha256:'+hashlib.sha256(data).hexdigest()}
                return {'id':7,'draft':False}
            result=publish_daily_release(directory,'frogiraffe/wildfire-signals','a'*40,api=api)
            self.assertEqual(result['uploaded'],2)
            self.assertEqual(result['tag'],'analysis-evidence-2026-10-12')
            self.assertEqual(calls[-1][0],'PATCH')
            self.assertIn(b'"draft": false',calls[-1][2])

    def test_existing_asset_is_never_replaced_on_digest_conflict(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            scan={'schema_version':1,'role':'firms_pixel_scan_receipt',
                  'scan_at':'2026-10-12T18:17:00+00:00','pixel_files':[],
                  'source_states':{'VIIRS_NOAA20_NRT':'complete','VIIRS_NOAA21_NRT':'complete'}}
            path=directory/'firms-pixel-scan-test.json.gz'
            path.write_bytes(gzip.compress(json.dumps(scan).encode(),mtime=0))
            def api(method,url,data=None,content_type=None):
                if method=='GET': return {'id':7,'draft':False,
                    'assets':[{'name':path.name,'digest':'sha256:'+'0'*64}]}
                raise AssertionError('must not mutate release')
            with self.assertRaisesRegex(ValueError,'digest conflict'):
                publish_daily_release(directory,'frogiraffe/wildfire-signals','a'*40,api=api)


if __name__=='__main__':
    unittest.main()
