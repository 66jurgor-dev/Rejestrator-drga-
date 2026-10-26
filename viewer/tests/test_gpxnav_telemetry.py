import pathlib
import sys
import tempfile
import unittest


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from trasy_app import parse_gpxnav


class GpxNavTelemetryTest(unittest.TestCase):
    def test_reads_shake_pulse_speed_and_ride_mode(self):
        document = """<?xml version="1.0" encoding="utf-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" xmlns:gpxnav="https://local/gpxnav/1" version="1.1" creator="test">
  <metadata><name>Test telemetryczny</name><gpxnav:navigation format="gpxnav" version="2" source="test.gpx" /></metadata>
  <trk><name>Test telemetryczny</name><trkseg>
    <trkpt lat="49.80000000" lon="20.00000000"><ele>400</ele><time>2026-07-01T10:00:00Z</time><extensions><gpxnav:telemetry heart_rate_bpm="100" wheel_speed_kmh="12.5" shake_score="18.25" ride_mode="jazda" /></extensions></trkpt>
    <trkpt lat="49.80010000" lon="20.00010000"><ele>402</ele><time>2026-07-01T10:00:01Z</time><extensions><gpxnav:telemetry heart_rate_bpm="105" wheel_speed_kmh="5.5" shake_score="72.75" ride_mode="prowadzenie" /></extensions></trkpt>
  </trkseg></trk>
</gpx>
"""
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "sample.gpxnav"
            path.write_text(document, encoding="utf-8")
            route = parse_gpxnav(path)

        self.assertEqual(len(route["profile"]), 2)
        first, second = route["profile"]
        self.assertEqual(first["heart_rate_bpm"], 100.0)
        self.assertEqual(first["wheel_speed_kmh"], 12.5)
        self.assertEqual(first["shake_score"], 18.25)
        self.assertEqual(first["ride_mode"], "jazda")
        self.assertEqual(second["ride_mode"], "prowadzenie")
        self.assertEqual(route["segments"], [])
        self.assertTrue(route["has_full_telemetry"])
        self.assertEqual(route["route_date"], "2026-07-01T10:00:00Z")


if __name__ == "__main__":
    unittest.main()
