import csv
import math
import pathlib
import struct
import tempfile
import unittest
import uuid

from test_vibbin_decoder import chunk, make_header, record
from vibbin_features import generate_features


class FeatureGeneratorTest(unittest.TestCase):
    def test_places_known_frequencies_in_expected_bands(self):
        session_id = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        start_utc_ms = 1_750_000_000_000
        start_ns = 70_000_000_000
        sample_rate = 50
        records = [
            record(5, start_ns, b"\x01\x02"),
        ]
        for index in range(sample_rate):
            time_s = index / sample_rate
            monotonic_ns = start_ns + int(time_s * 1_000_000_000)
            acc = math.sin(2 * math.pi * 3 * time_s)
            gyro = math.sin(2 * math.pi * 18 * time_s)
            records.append(record(1, monotonic_ns, struct.pack(">fff", 0.0, 0.0, acc)))
            records.append(record(2, monotonic_ns + 1, struct.pack(">fff", 0.0, 0.0, gyro)))
        source_bytes = make_header(session_id, start_utc_ms, start_ns) + chunk(0, records, start_ns)

        with tempfile.TemporaryDirectory() as folder:
            source = pathlib.Path(folder) / "frequencies.bin"
            output = pathlib.Path(folder) / "features.csv"
            source.write_bytes(source_bytes)
            summary = generate_features(source, output, 1.0)
            self.assertEqual(summary["rows"], 1)
            with output.open(encoding="utf-8-sig", newline="") as stream:
                row = next(csv.DictReader(stream))
            self.assertGreater(float(row["acc_dyn_z_band_1_5_ratio"]), 0.95)
            self.assertGreater(float(row["gyro_z_band_12_25_ratio"]), 0.95)
            self.assertEqual(row["ride_mode"], "jazda")
            self.assertEqual(row["surface_type"], "stabilna_nat")
            self.assertEqual(row["label_changed"], "0")

    def test_backup_part_starts_at_first_real_window(self):
        session_id = uuid.UUID("11111111-2222-3333-4444-555555555555")
        start_utc_ms = 1_750_000_000_000
        start_ns = 10_000_000_000
        backup_start_ns = start_ns + 600_200_000_000
        records = [
            record(6, backup_start_ns, struct.pack(">q", start_utc_ms + 600_200)),
            record(5, backup_start_ns, b"\x01\x01"),
            record(1, backup_start_ns, struct.pack(">fff", 0.0, 0.0, 9.81)),
            record(2, backup_start_ns + 1, struct.pack(">fff", 0.0, 0.0, 0.0)),
        ]
        source_bytes = make_header(session_id, start_utc_ms, start_ns) + chunk(600, records, backup_start_ns)

        with tempfile.TemporaryDirectory() as folder:
            source = pathlib.Path(folder) / "part-002.bin"
            output = pathlib.Path(folder) / "features.csv"
            source.write_bytes(source_bytes)
            summary = generate_features(source, output, 1.0)
            self.assertEqual(summary["rows"], 1)
            with output.open(encoding="utf-8-sig", newline="") as stream:
                row = next(csv.DictReader(stream))
            self.assertAlmostEqual(float(row["elapsed_s"]), 600.0)


if __name__ == "__main__":
    unittest.main()
