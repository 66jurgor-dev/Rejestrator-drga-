#!/usr/bin/env python3
"""Decode VIBRAW v1 files to a human-readable event CSV."""

from __future__ import annotations

import argparse
import contextlib
import csv
import datetime as dt
import math
import pathlib
import struct
import sys
import uuid
import zlib
from collections import Counter


FILE_MAGIC = b"VIBRAW01"
CHUNK_MAGIC = b"CHNK"
HEADER_SIZE = 64
FORMAT_VERSION = 1

EVENT_NAMES = {
    1: "ACC",
    2: "GYRO",
    3: "HEART_RATE",
    4: "WHEEL",
    5: "LABEL",
    6: "TIME_SYNC",
    7: "STATUS",
    8: "SESSION",
}
RIDE_MODES = {0: "unknown", 1: "jazda", 2: "prowadzenie"}
SURFACES = {
    0: "unknown",
    1: "twarda",
    2: "stabilna_nat",
    3: "nierownosci_stab",
    4: "ruchoma_drob",
    5: "ruchoma_grub",
    6: "rynna",
    7: "miekkie",
    8: "regularne_twar",
    9: "brak",
}
STATUS_SOURCES = {1: "service", 2: "heart_rate", 3: "wheel"}
SESSION_EVENTS = {1: "start", 2: "stop"}

CSV_FIELDS = [
    "session_id",
    "format_version",
    "event_index",
    "chunk_sequence",
    "event_type",
    "utc_time_iso",
    "utc_ms",
    "monotonic_time_ns",
    "acc_x",
    "acc_y",
    "acc_z",
    "gyro_x",
    "gyro_y",
    "gyro_z",
    "heart_rate_bpm",
    "wheel_revolutions_total",
    "wheel_event_time_1024",
    "wheel_speed_kmh",
    "ride_mode",
    "surface_type",
    "status_source",
    "status_text",
    "session_event",
]


class DecodeError(Exception):
    pass


def parse_header(data: bytes) -> dict[str, object]:
    if len(data) != HEADER_SIZE:
        raise DecodeError("File is shorter than the 64-byte header")
    if data[:8] != FILE_MAGIC:
        raise DecodeError("Invalid file magic")
    expected_crc = struct.unpack_from(">I", data, 60)[0]
    actual_crc = zlib.crc32(data[:60]) & 0xFFFFFFFF
    if actual_crc != expected_crc:
        raise DecodeError("Header CRC mismatch")

    version, header_size = struct.unpack_from(">HH", data, 8)
    if version != FORMAT_VERSION:
        raise DecodeError(f"Unsupported format version: {version}")
    if header_size != HEADER_SIZE:
        raise DecodeError(f"Unsupported header size: {header_size}")

    start_utc_ms, start_mono_ns, uuid_most, uuid_least = struct.unpack_from(">qqQQ", data, 12)
    sensor_period_us, wheel_circumference_mm, flags, _reserved = struct.unpack_from(">iiii", data, 44)
    session_int = (uuid_most << 64) | uuid_least
    return {
        "format_version": version,
        "start_utc_ms": start_utc_ms,
        "start_monotonic_ns": start_mono_ns,
        "session_id": str(uuid.UUID(int=session_int)),
        "sensor_period_us": sensor_period_us,
        "wheel_circumference_mm": wheel_circumference_mm,
        "flags": flags,
    }


def utc_iso(utc_ms: float) -> str:
    timestamp = dt.datetime.fromtimestamp(utc_ms / 1000.0, tz=dt.timezone.utc)
    return timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def decode_file(
    input_path: pathlib.Path,
    output_path: pathlib.Path | None,
    row_callback=None,
) -> dict[str, object]:
    counts: Counter[str] = Counter()
    valid_chunks = 0
    recovered_tail = False
    event_index = 0

    with input_path.open("rb") as source, contextlib.ExitStack() as stack:
        header = parse_header(source.read(HEADER_SIZE))
        anchor_mono_ns = int(header["start_monotonic_ns"])
        anchor_utc_ms = int(header["start_utc_ms"])
        ride_mode = "unknown"
        surface_type = "unknown"

        writer = None
        if output_path is not None:
            target = stack.enter_context(output_path.open("w", newline="", encoding="utf-8-sig"))
            writer = csv.DictWriter(target, fieldnames=CSV_FIELDS)
            writer.writeheader()

        while True:
                chunk_header = source.read(32)
                if not chunk_header:
                    break
                if len(chunk_header) < 32:
                    recovered_tail = True
                    break
                if chunk_header[:4] != CHUNK_MAGIC:
                    raise DecodeError(f"Invalid chunk magic at chunk {valid_chunks}")

                sequence, record_count, payload_size = struct.unpack_from(">III", chunk_header, 4)
                _first_mono_ns = struct.unpack_from(">q", chunk_header, 16)[0]
                payload_crc, header_crc = struct.unpack_from(">II", chunk_header, 24)
                if (zlib.crc32(chunk_header[4:28]) & 0xFFFFFFFF) != header_crc:
                    raise DecodeError(f"Chunk {sequence} header CRC mismatch")

                payload = source.read(payload_size)
                if len(payload) < payload_size:
                    recovered_tail = True
                    break
                if (zlib.crc32(payload) & 0xFFFFFFFF) != payload_crc:
                    raise DecodeError(f"Chunk {sequence} payload CRC mismatch")

                offset = 0
                decoded_in_chunk = 0
                while offset < len(payload):
                    if offset + 3 > len(payload):
                        raise DecodeError(f"Truncated record prefix in chunk {sequence}")
                    event_type, record_size = struct.unpack_from(">BH", payload, offset)
                    offset += 3
                    end = offset + record_size
                    if record_size < 8 or end > len(payload):
                        raise DecodeError(f"Invalid record size in chunk {sequence}")

                    record = memoryview(payload)[offset:end]
                    monotonic_ns = struct.unpack_from(">q", record, 0)[0]
                    event_name = EVENT_NAMES.get(event_type, f"UNKNOWN_{event_type}")
                    calculated_utc_ms = anchor_utc_ms + (monotonic_ns - anchor_mono_ns) / 1_000_000.0
                    row = {field: "" for field in CSV_FIELDS}
                    row.update(
                        session_id=header["session_id"],
                        format_version=header["format_version"],
                        event_index=event_index,
                        chunk_sequence=sequence,
                        event_type=event_name,
                        utc_time_iso=utc_iso(calculated_utc_ms),
                        utc_ms=f"{calculated_utc_ms:.3f}",
                        monotonic_time_ns=monotonic_ns,
                        ride_mode=ride_mode,
                        surface_type=surface_type,
                    )

                    if event_type in (1, 2) and record_size == 20:
                        x, y, z = struct.unpack_from(">fff", record, 8)
                        prefix = "acc" if event_type == 1 else "gyro"
                        row[f"{prefix}_x"] = f"{x:.9g}"
                        row[f"{prefix}_y"] = f"{y:.9g}"
                        row[f"{prefix}_z"] = f"{z:.9g}"
                    elif event_type == 3 and record_size == 10:
                        row["heart_rate_bpm"] = struct.unpack_from(">H", record, 8)[0]
                    elif event_type == 4 and record_size == 18:
                        revolutions, event_time, speed = struct.unpack_from(">IHf", record, 8)
                        row["wheel_revolutions_total"] = revolutions
                        row["wheel_event_time_1024"] = event_time
                        row["wheel_speed_kmh"] = "" if math.isnan(speed) else f"{speed:.6g}"
                    elif event_type == 5 and record_size == 10:
                        mode_code, surface_code = struct.unpack_from(">BB", record, 8)
                        ride_mode = RIDE_MODES.get(mode_code, f"unknown_{mode_code}")
                        surface_type = SURFACES.get(surface_code, f"unknown_{surface_code}")
                        row["ride_mode"] = ride_mode
                        row["surface_type"] = surface_type
                    elif event_type == 6 and record_size == 16:
                        synced_utc_ms = struct.unpack_from(">q", record, 8)[0]
                        anchor_mono_ns = monotonic_ns
                        anchor_utc_ms = synced_utc_ms
                        row["utc_ms"] = str(synced_utc_ms)
                        row["utc_time_iso"] = utc_iso(synced_utc_ms)
                    elif event_type == 7 and record_size >= 11:
                        source_code, text_size = struct.unpack_from(">BH", record, 8)
                        if 11 + text_size != record_size:
                            raise DecodeError(f"Invalid STATUS size in chunk {sequence}")
                        row["status_source"] = STATUS_SOURCES.get(source_code, f"unknown_{source_code}")
                        row["status_text"] = bytes(record[11 : 11 + text_size]).decode("utf-8", errors="replace")
                    elif event_type == 8 and record_size == 9:
                        code = record[8]
                        row["session_event"] = SESSION_EVENTS.get(code, f"unknown_{code}")
                    else:
                        raise DecodeError(
                            f"Unsupported record type/size {event_type}/{record_size} in chunk {sequence}"
                        )

                    if writer is not None:
                        writer.writerow(row)
                    if row_callback is not None:
                        row_callback(row)
                    counts[event_name] += 1
                    event_index += 1
                    decoded_in_chunk += 1
                    offset = end

                if decoded_in_chunk != record_count:
                    raise DecodeError(
                        f"Chunk {sequence} declares {record_count} records, decoded {decoded_in_chunk}"
                    )
                valid_chunks += 1

    return {
        **header,
        "valid_chunks": valid_chunks,
        "events": event_index,
        "counts": dict(counts),
        "recovered_incomplete_tail": recovered_tail,
        "output": str(output_path) if output_path is not None else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=pathlib.Path, help="input .bin file")
    parser.add_argument("output", type=pathlib.Path, nargs="?", help="output event CSV")
    args = parser.parse_args()
    output = args.output or args.input.with_suffix(".events.csv")
    try:
        summary = decode_file(args.input, output)
    except (OSError, DecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"session_id={summary['session_id']}")
    print(f"events={summary['events']} valid_chunks={summary['valid_chunks']}")
    print(f"event_counts={summary['counts']}")
    print(f"recovered_incomplete_tail={summary['recovered_incomplete_tail']}")
    print(f"output={summary['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
