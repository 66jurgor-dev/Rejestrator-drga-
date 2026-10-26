import csv
import pathlib
import struct
import tempfile
import unittest
import uuid
import zlib

from vibbin_decoder import decode_file


def make_header(session_id, start_utc_ms, start_mono_ns):
    header = bytearray(64)
    struct.pack_into(">8sHHqqQQiiii", header, 0, b"VIBRAW01", 1, 64, start_utc_ms, start_mono_ns,
                     session_id.int >> 64, session_id.int & ((1 << 64) - 1), 20000, 2200, 0, 0)
    struct.pack_into(">I", header, 60, zlib.crc32(header[:60]) & 0xFFFFFFFF)
    return bytes(header)


def record(record_type, monotonic_ns, body=b""):
    content = struct.pack(">q", monotonic_ns) + body
    return struct.pack(">BH", record_type, len(content)) + content


def chunk(sequence, records, first_mono_ns):
    payload = b"".join(records)
    data = struct.pack(">IIIqI", sequence, len(records), len(payload), first_mono_ns,
                       zlib.crc32(payload) & 0xFFFFFFFF)
    return b"CHNK" + data + struct.pack(">I", zlib.crc32(data) & 0xFFFFFFFF) + payload


class DecoderTest(unittest.TestCase):
    def test_decodes_events_and_recovers_truncated_tail(self):
        session_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        start_utc_ms = 1_750_000_000_000
        start_mono_ns = 50_000_000_000
        records = [
            record(8, start_mono_ns, b"\x01"),
            record(6, start_mono_ns, struct.pack(">q", start_utc_ms)),
            record(5, start_mono_ns, b"\x01\x04"),
            record(1, start_mono_ns + 20_000_000, struct.pack(">fff", 1.0, 2.0, 3.0)),
            record(2, start_mono_ns + 21_000_000, struct.pack(">fff", 0.1, 0.2, 0.3)),
            record(3, start_mono_ns + 22_000_000, struct.pack(">H", 142)),
            record(4, start_mono_ns + 23_000_000, struct.pack(">IHf", 123, 456, 17.5)),
        ]
        valid = make_header(session_id, start_utc_ms, start_mono_ns) + chunk(0, records, start_mono_ns)

        with tempfile.TemporaryDirectory() as folder:
            source = pathlib.Path(folder) / "sample.bin"
            output = pathlib.Path(folder) / "sample.csv"
            source.write_bytes(valid + b"CHNK\x00")
            summary = decode_file(source, output)

            self.assertEqual(summary["events"], len(records))
            self.assertEqual(summary["valid_chunks"], 1)
            self.assertTrue(summary["recovered_incomplete_tail"])
            with output.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[3]["acc_x"], "1")
            self.assertEqual(rows[3]["ride_mode"], "jazda")
            self.assertEqual(rows[3]["surface_type"], "ruchoma_drob")
            self.assertEqual(rows[5]["heart_rate_bpm"], "142")
            self.assertEqual(rows[6]["wheel_speed_kmh"], "17.5")


if __name__ == "__main__":
    unittest.main()
