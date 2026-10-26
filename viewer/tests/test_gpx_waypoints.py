import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trasy_app import gpxnav_waypoints, parse_plain_gpx


class GpxWaypointTests(unittest.TestCase):
    def test_plain_gpx_exposes_embedded_waypoints(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1" creator="test">
  <wpt lat="49.123" lon="19.456">
    <ele>712.4</ele><name>Schronisko</name><cmt>Postój</cmt>
    <desc>Bufet i woda</desc><sym>Lodge</sym><type>POI</type>
  </wpt>
  <trk><name>Test</name><trkseg>
    <trkpt lat="49.1" lon="19.4"><ele>700</ele></trkpt>
    <trkpt lat="49.2" lon="19.5"><ele>710</ele></trkpt>
  </trkseg></trk>
</gpx>"""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "waypoints.gpx"
            path.write_text(xml, encoding="utf-8")
            route = parse_plain_gpx(path)

        self.assertEqual(len(route["waypoints"]), 1)
        waypoint = route["waypoints"][0]
        self.assertEqual(waypoint["name"], "Schronisko")
        self.assertEqual(waypoint["description"], "Bufet i woda")
        self.assertEqual(waypoint["comment"], "Postój")
        self.assertEqual(waypoint["symbol"], "Lodge")
        self.assertEqual(waypoint["type"], "POI")
        self.assertAlmostEqual(waypoint["ele"], 712.4)

    def test_gpxnav_falls_back_to_named_source_gpx(self):
        source_xml = """<gpx xmlns="http://www.topografix.com/GPX/1/1">
  <wpt lat="49.5615" lon="20.1155"><name>SCHODY</name><sym>Crossing</sym></wpt>
  <trk><name>Turbacz</name><trkseg /></trk>
</gpx>"""
        nav_xml = """<gpx xmlns="http://www.topografix.com/GPX/1/1" xmlns:gpxnav="https://local/gpxnav/1">
  <metadata><gpxnav:navigation source="2026-07-29 Turbacz.gpx" /></metadata>
</gpx>"""
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "Turbacz" / "2026-07-29 Turbacz.gpx"
            source.parent.mkdir()
            source.write_text(source_xml, encoding="utf-8")
            waypoints = gpxnav_waypoints(ET.fromstring(nav_xml), Path(folder))

        self.assertEqual(len(waypoints), 1)
        self.assertEqual(waypoints[0]["name"], "SCHODY")
        self.assertEqual(waypoints[0]["symbol"], "Crossing")


if __name__ == "__main__":
    unittest.main()
