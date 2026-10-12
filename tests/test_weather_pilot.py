"""A fetched forecast is available only after its actual receipt time."""
import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fire_public.history import HistoryStore
from fire_public.weather_pilot import _fetch_json, nws_grid_record, replay_pilot, run_pilot

GRID_URL = "https://api.weather.gov/gridpoints/TOP/32,81"
AT = "2026-10-12T02:00:00+00:00"
GRID = {"properties": {"updateTime": "2026-10-12T01:00:00+00:00",
    "validTimes": "2026-10-12T01:00:00+00:00/P7D",
    "windSpeed": {"uom": "wmoUnit:km_h-1", "values": [
        {"validTime": "2026-10-12T01:00:00+00:00/PT6H", "value": 20}]},
    "windDirection": {"uom": "wmoUnit:degree_(angle)", "values": [
        {"validTime": "2026-10-12T01:00:00+00:00/PT6H", "value": 270}]},
    "windGust": {"uom": "wmoUnit:km_h-1", "values": [
        {"validTime": "2026-10-12T01:00:00+00:00/PT6H", "value": 30}]},
    "temperature": {"uom": "wmoUnit:degC", "values": [
        {"validTime": "2026-10-12T01:00:00+00:00/PT6H", "value": 28}]},
    "relativeHumidity": {"uom": "wmoUnit:percent", "values": [
        {"validTime": "2026-10-12T01:00:00+00:00/PT6H", "value": 35}]},
    "quantitativePrecipitation": {"uom": "wmoUnit:mm", "values": [
        {"validTime": "2026-10-12T01:00:00+00:00/PT6H", "value": 0}]}}}


class WeatherPilotTests(unittest.TestCase):
    def test_forecast_retains_source_intervals_and_as_of_capture_gate(self):
        raw = json.dumps(GRID).encode()
        record = nws_grid_record(GRID, latitude=39.7456, longitude=-97.0892,
                                 grid_url=GRID_URL, captured_at=AT,
                                 raw_sha256=hashlib.sha256(raw).hexdigest())
        self.assertEqual(record["subject_kind"], "weather_forecast_snapshot")
        self.assertEqual(record["observed_at"], GRID["properties"]["updateTime"])
        self.assertEqual(record["payload"]["fields"]["windSpeed"]["values"][0]
                         ["validTime"], "2026-10-12T01:00:00+00:00/PT6H")
        with tempfile.TemporaryDirectory() as temp:
            store = HistoryStore(Path(temp) / "weather.sqlite3")
            self.addCleanup(store.close)
            store.append(record)
            self.assertEqual(store.as_of("2026-10-12T01:30:00Z", "nws_grid:TOP/32,81"), [])
            self.assertEqual(len(store.as_of(AT, "nws_grid:TOP/32,81")), 1)
            self.assertIsNone(store.fire_event_for("nws_grid", "TOP/32,81"))

    def test_forecast_rejects_hostile_url_future_update_and_bad_units(self):
        args = dict(latitude=39.7, longitude=-97.1, captured_at=AT,
                    raw_sha256="a" * 64)
        with self.assertRaises(ValueError):
            nws_grid_record(GRID, grid_url="https://example.com/forecast", **args)
        future = json.loads(json.dumps(GRID))
        future["properties"]["updateTime"] = "2026-10-12T03:00:00Z"
        with self.assertRaises(ValueError):
            nws_grid_record(future, grid_url=GRID_URL, **args)
        wrong_unit = json.loads(json.dumps(GRID))
        wrong_unit["properties"]["windSpeed"]["uom"] = "wmoUnit:kn"
        with self.assertRaises(ValueError):
            nws_grid_record(wrong_unit, grid_url=GRID_URL, **args)
        wrong_interval = json.loads(json.dumps(GRID))
        wrong_interval["properties"]["windSpeed"]["values"][0]["validTime"] = "2026-10-12T01:00:00Z/PT"
        with self.assertRaises(ValueError):
            nws_grid_record(wrong_interval, grid_url=GRID_URL, **args)
        wrong_value = json.loads(json.dumps(GRID))
        wrong_value["properties"]["relativeHumidity"]["values"][0]["value"] = True
        with self.assertRaises(ValueError):
            nws_grid_record(wrong_value, grid_url=GRID_URL, **args)

    def test_raw_manifest_replays_and_rejects_corruption(self):
        point = {"geometry": {"type": "Point", "coordinates": [-97.0892, 39.7456]},
                 "properties": {"forecastGridData": GRID_URL,
                                "gridId": "TOP", "gridX": 32, "gridY": 81}}
        point_raw = json.dumps(point).encode()
        grid_raw = json.dumps(GRID).encode()
        answers = [(point,point_raw),(GRID,grid_raw)]
        with tempfile.TemporaryDirectory() as temp, \
                patch("fire_public.weather_pilot._fetch_json", side_effect=answers), \
                patch("fire_public.weather_pilot._received_at",
                      side_effect=["2026-10-12T01:50:00Z", "2026-10-12T01:55:00Z", AT]):
            db = Path(temp) / "weather.sqlite3"
            raw_dir = Path(temp) / "raw"
            report = run_pilot(db,raw_dir,latitude=39.7456,longitude=-97.0892)
            self.assertEqual(report["schema_version"],1)
            self.assertEqual(report["point_captured_at"],"2026-10-12T01:55:00Z")
            self.assertEqual(report["grid_captured_at"],AT)
            replay_db = Path(temp) / "replay.sqlite3"
            replay_pilot(raw_dir,replay_db)
            self.assertEqual(db.read_bytes(),replay_db.read_bytes())
            manifest_path = raw_dir / "weather-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["grid_captured_at"] = "2026-10-12T01:58:00Z"
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "commitment"):
                replay_pilot(raw_dir,Path(temp) / "backdated.sqlite3")
            self.assertFalse((Path(temp) / "backdated.sqlite3").exists())
            manifest_path.write_text(json.dumps(report))
            raw_hash = report["grid_sha256"]
            (raw_dir / f"{raw_hash}.json.gz").write_bytes(gzip.compress(b"{}"))
            with self.assertRaises(ValueError):
                replay_pilot(raw_dir,Path(temp) / "corrupt.sqlite3")

    def test_pilot_rejects_point_location_mismatch_before_grid_request(self):
        point = {"geometry": {"type": "Point", "coordinates": [-80, 39.7456]},
                 "properties": {"forecastGridData": GRID_URL,
                                "gridId": "TOP", "gridX": 32, "gridY": 81}}
        with tempfile.TemporaryDirectory() as temp, \
                patch("fire_public.weather_pilot._fetch_json",
                      return_value=(point,json.dumps(point).encode())) as fetch:
            with self.assertRaises(ValueError):
                run_pilot(Path(temp) / "db.sqlite3", Path(temp) / "raw",
                          latitude=39.7456,longitude=-97.0892)
            self.assertEqual(fetch.call_count,1)
            self.assertFalse((Path(temp) / "db.sqlite3").exists())
            self.assertFalse((Path(temp) / "raw").exists())

    def test_failed_database_write_leaves_no_published_outputs(self):
        point = {"geometry": {"type": "Point", "coordinates": [-97.0892, 39.7456]},
                 "properties": {"forecastGridData": GRID_URL,
                                "gridId": "TOP", "gridX": 32, "gridY": 81}}
        answers = [(point, json.dumps(point).encode()), (GRID, json.dumps(GRID).encode())]
        with tempfile.TemporaryDirectory() as temp, \
                patch("fire_public.weather_pilot._fetch_json", side_effect=answers), \
                patch("fire_public.weather_pilot._received_at",
                      side_effect=["2026-10-12T01:50:00Z", "2026-10-12T01:55:00Z", AT]), \
                patch("fire_public.weather_pilot.HistoryStore.append", side_effect=OSError("disk")):
            db = Path(temp) / "db.sqlite3"
            raw_dir = Path(temp) / "raw"
            with self.assertRaises(OSError):
                run_pilot(db, raw_dir, latitude=39.7456, longitude=-97.0892)
            self.assertFalse(db.exists())
            self.assertFalse(raw_dir.exists())

    def test_request_rejects_redirect_to_other_host(self):
        from urllib.request import Request
        class RedirectingOpener:
            def open(self, request, timeout):
                raise ValueError("redirect rejected")
        with patch("fire_public.weather_pilot.build_opener") as make_opener:
            make_opener.return_value = RedirectingOpener()
            with self.assertRaisesRegex(ValueError, "redirect rejected"):
                _fetch_json("https://api.weather.gov/gridpoints/TOP/32,81")
            handler = make_opener.call_args.args[0]
            with self.assertRaisesRegex(ValueError, "redirect rejected"):
                handler.redirect_request(Request(GRID_URL), None, 302, "redirect", {},
                                         "https://example.com/")


if __name__ == "__main__":
    unittest.main()
