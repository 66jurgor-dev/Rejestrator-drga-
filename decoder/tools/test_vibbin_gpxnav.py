import datetime as dt
import pathlib
import struct
import tempfile
import unittest
import uuid
import xml.etree.ElementTree as ET
import zlib

from vibbin_gpxnav import GPXNAV_NS, generate_gpxnav, local_name


def make_header(session_id, start_utc_ms, start_mono_ns):
    header = bytearray(64)
    struct.pack_into(
        ">8sHHqqQQiiii",
        header,
        0,
        b"VIBRAW01",
        1,
        64,
        start_utc_ms,
        start_mono_ns,
        session_id.int >> 64,
        session_id.int & ((1 << 64) - 1),
        20000,
        2100,
        0,
        0,
    )
    struct.pack_into(">I", header, 60, zlib.crc32(header[:60]) & 0xFFFFFFFF)
    return bytes(header)


def record(record_type, monotonic_ns, body=b""):
    content = struct.pack(">q", monotonic_ns) + body
    return struct.pack(">BH", record_type, len(content)) + content


def chunk(records, first_mono_ns):
    payload = b"".join(records)
    data = struct.pack(">IIIqI", 0, len(records), len(payload), first_mono_ns, zlib.crc32(payload) & 0xFFFFFFFF)
    return b"CHNK" + data + struct.pack(">I", zlib.crc32(data) & 0xFFFFFFFF) + payload


class GpxNavTest(unittest.TestCase):
    def test_merges_shake_score_heart_rate_and_wheel_speed(self):
        start_utc_ms = 1_750_000_000_000
        start_mono_ns = 50_000_000_000
        records = [
            record(6, start_mono_ns, struct.pack(">q", start_utc_ms)),
            record(5, start_mono_ns, b"\x01\x01"),
            record(3, start_mono_ns, struct.pack(">H", 100)),
            record(4, start_mono_ns, struct.pack(">IHf", 1, 100, 10.0)),
            record(2, start_mono_ns + 100_000_000, struct.pack(">fff", 0.0, 0.0, 0.2)),
            record(2, start_mono_ns + 500_000_000, struct.pack(">fff", 0.0, 0.0, 1.0)),
            record(2, start_mono_ns + 1_100_000_000, struct.pack(">fff", 0.0, 0.0, 0.4)),
            record(2, start_mono_ns + 1_800_000_000, struct.pack(">fff", 0.0, 0.0, 2.0)),
            record(5, start_mono_ns + 2_000_000_000, b"\x02\x06"),
            record(3, start_mono_ns + 2_000_000_000, struct.pack(">H", 120)),
            record(4, start_mono_ns + 2_000_000_000, struct.pack(">IHf", 2, 200, 5.0)),
        ]
        binary = make_header(uuid.uuid4(), start_utc_ms, start_mono_ns) + chunk(records, start_mono_ns)
        start = dt.datetime.fromtimestamp(start_utc_ms / 1000, tz=dt.timezone.utc)
        points = []
        for index in range(4):
            timestamp = (start + dt.timedelta(seconds=index)).isoformat().replace("+00:00", "Z")
            points.append(
                f'<trkpt lat="49.{800000 + index:06d}" lon="20.{index:06d}"><ele>{400 + index}</ele>'
                f"<time>{timestamp}</time></trkpt>"
            )
        gpx = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1" creator="test">'
            "<trk><name>Test</name><trkseg>" + "".join(points) + "</trkseg></trk></gpx>"
        )

        with tempfile.TemporaryDirectory() as folder:
            bin_path = pathlib.Path(folder) / "sample.bin"
            gpx_path = pathlib.Path(folder) / "sample.gpx"
            output = pathlib.Path(folder) / "sample.gpxnav"
            bin_path.write_bytes(binary)
            gpx_path.write_text(gpx, encoding="utf-8")
            summary = generate_gpxnav(bin_path, gpx_path, output)

            self.assertEqual(summary["points"], 4)
            self.assertEqual(summary["segments"], 0)
            self.assertEqual(summary["shake_windows"], 2)
            self.assertEqual(summary["telemetry_points"], 4)
            root = ET.parse(output).getroot()
            segments = [element for element in root.iter() if element.tag == f"{{{GPXNAV_NS}}}segment"]
            self.assertEqual(segments, [])
            telemetry = [element for element in root.iter() if local_name(element.tag) == "telemetry"]
            self.assertEqual(telemetry[0].attrib["heart_rate_bpm"], "100")
            self.assertEqual(telemetry[0].attrib["wheel_speed_kmh"], "10.000")
            self.assertEqual(telemetry[-1].attrib["heart_rate_bpm"], "120")
            self.assertEqual(telemetry[-1].attrib["wheel_speed_kmh"], "5.000")
            self.assertGreater(float(telemetry[0].attrib["shake_score"]), 0.0)
            self.assertGreater(float(telemetry[-1].attrib["shake_score"]), 0.0)
            self.assertEqual(telemetry[0].attrib["ride_mode"], "jazda")
            self.assertEqual(telemetry[-1].attrib["ride_mode"], "prowadzenie")


if __name__ == "__main__":
    unittest.main()
