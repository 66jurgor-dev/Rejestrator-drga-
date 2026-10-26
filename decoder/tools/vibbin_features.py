#!/usr/bin/env python3
"""Generate windowed ML features directly from a VIBRAW v1 file."""

from __future__ import annotations

import argparse
import contextlib
import csv
import math
import pathlib
import struct
import sys
import zlib
from dataclasses import dataclass, field

import numpy as np

from vibbin_decoder import (
    CHUNK_MAGIC,
    HEADER_SIZE,
    RIDE_MODES,
    SURFACES,
    DecodeError,
    parse_header,
    utc_iso,
)


FEATURE_SUFFIXES = [
    "mean_abs",
    "rms",
    "max_abs",
    "p95_abs",
    "peak_to_peak",
    "mean_abs_delta",
    "delta_rms",
    "max_abs_delta",
    "zero_crossings",
    "band_1_5_energy",
    "band_5_12_energy",
    "band_12_25_energy",
    "band_1_5_ratio",
    "band_5_12_ratio",
    "band_12_25_ratio",
]
ACC_PREFIXES = ["acc_dyn_x", "acc_dyn_y", "acc_dyn_z", "acc_dyn_3d"]
GYRO_PREFIXES = ["gyro_x", "gyro_y", "gyro_z", "gyro_3d"]

BASE_FIELDS = [
    "time_iso",
    "elapsed_s",
    "window_s",
    "sample_count",
    "sample_rate_hz",
    "x_mean",
    "y_mean",
    "z_mean",
]
GYRO_BASE_FIELDS = [
    "gyro_sample_count",
    "gyro_rate_hz",
    "gyro_x_mean",
    "gyro_y_mean",
    "gyro_z_mean",
]
CONTEXT_FIELDS = [
    "wheel_revolutions_total",
    "wheel_event_time_1024",
    "wheel_speed_kmh",
    "wheel_age_s",
    "heart_rate_bpm",
    "heart_rate_age_s",
    "ride_mode",
    "surface_type",
    "label_changed",
]


def feature_fields(prefixes):
    return [f"{prefix}_{suffix}" for prefix in prefixes for suffix in FEATURE_SUFFIXES]


CSV_FIELDS = (
    BASE_FIELDS
    + feature_fields(ACC_PREFIXES)
    + GYRO_BASE_FIELDS
    + feature_fields(GYRO_PREFIXES)
    + CONTEXT_FIELDS
)


@dataclass
class WindowState:
    start_ns: int
    end_ns: int
    acc: list[tuple[float, float, float]] = field(default_factory=list)
    gyro: list[tuple[float, float, float]] = field(default_factory=list)
    label_changed: bool = False


@dataclass
class ContextState:
    ride_mode: str = "unknown"
    surface_type: str = "unknown"
    heart_rate_bpm: int | None = None
    heart_rate_ns: int | None = None
    wheel_revolutions: int | None = None
    wheel_event_time: int | None = None
    wheel_speed_kmh: float | None = None
    wheel_ns: int | None = None
    anchor_monotonic_ns: int = 0
    anchor_utc_ms: int = 0


def iter_records(input_path: pathlib.Path):
    with input_path.open("rb") as source:
        header = parse_header(source.read(HEADER_SIZE))
        while True:
            chunk_header = source.read(32)
            if not chunk_header:
                return header
            if len(chunk_header) < 32:
                return header
            if chunk_header[:4] != CHUNK_MAGIC:
                raise DecodeError("Invalid chunk magic")
            sequence, record_count, payload_size = struct.unpack_from(">III", chunk_header, 4)
            payload_crc, header_crc = struct.unpack_from(">II", chunk_header, 24)
            if (zlib.crc32(chunk_header[4:28]) & 0xFFFFFFFF) != header_crc:
                raise DecodeError(f"Chunk {sequence} header CRC mismatch")
            payload = source.read(payload_size)
            if len(payload) < payload_size:
                return header
            if (zlib.crc32(payload) & 0xFFFFFFFF) != payload_crc:
                raise DecodeError(f"Chunk {sequence} payload CRC mismatch")

            offset = 0
            decoded = 0
            while offset < len(payload):
                event_type, record_size = struct.unpack_from(">BH", payload, offset)
                offset += 3
                end = offset + record_size
                if record_size < 8 or end > len(payload):
                    raise DecodeError(f"Invalid record size in chunk {sequence}")
                record = memoryview(payload)[offset:end]
                monotonic_ns = struct.unpack_from(">q", record, 0)[0]
                yield header, event_type, monotonic_ns, record
                offset = end
                decoded += 1
            if decoded != record_count:
                raise DecodeError(f"Chunk {sequence} record count mismatch")


def band_features(signal: np.ndarray, sample_rate_hz: float):
    if signal.size < 4 or sample_rate_hz <= 0:
        return (0.0,) * 6
    centered = signal - signal.mean()
    window = np.hanning(signal.size)
    window_squares = float(np.dot(window, window))
    if window_squares <= 0:
        return (0.0,) * 6
    spectrum = np.fft.rfft(centered * window)
    power = np.abs(spectrum) ** 2 / (signal.size * window_squares)
    if signal.size > 2:
        if signal.size % 2 == 0:
            power[1:-1] *= 2.0
        else:
            power[1:] *= 2.0
    frequencies = np.fft.rfftfreq(signal.size, d=1.0 / sample_rate_hz)
    low = float(power[(frequencies >= 1.0) & (frequencies < 5.0)].sum())
    mid = float(power[(frequencies >= 5.0) & (frequencies < 12.0)].sum())
    high = float(power[(frequencies >= 12.0) & (frequencies <= 25.0)].sum())
    total = low + mid + high
    if total <= 1e-12:
        return low, mid, high, 0.0, 0.0, 0.0
    return low, mid, high, low / total, mid / total, high / total


def signal_features(signal: np.ndarray, sample_rate_hz: float):
    if signal.size == 0:
        return [0.0] * len(FEATURE_SUFFIXES)
    absolute = np.abs(signal)
    sorted_abs = np.sort(absolute)
    p95_index = max(0, math.ceil(signal.size * 0.95) - 1)
    differences = np.diff(signal)
    rms = float(np.sqrt(np.mean(signal * signal)))
    centered = signal - float(signal.mean())
    deadband = max(1e-6, rms * 0.05)
    signs = np.where(centered > deadband, 1, np.where(centered < -deadband, -1, 0))
    nonzero_signs = signs[signs != 0]
    zero_crossings = int(np.count_nonzero(nonzero_signs[1:] != nonzero_signs[:-1]))
    bands = band_features(signal, sample_rate_hz)
    return [
        float(absolute.mean()),
        rms,
        float(absolute.max()),
        float(sorted_abs[p95_index]),
        float(signal.max() - signal.min()),
        float(np.abs(differences).mean()) if differences.size else 0.0,
        float(np.sqrt(np.mean(differences * differences))) if differences.size else 0.0,
        float(np.abs(differences).max()) if differences.size else 0.0,
        zero_crossings,
        *bands,
    ]


def vector_feature_sets(samples, sample_rate_hz, center_axes):
    if not samples:
        empty = [0.0] * len(FEATURE_SUFFIXES)
        return [empty, empty, empty, empty], [0.0, 0.0, 0.0]
    array = np.asarray(samples, dtype=np.float64)
    means = array.mean(axis=0)
    feature_axes = array - means if center_axes else array
    magnitude = np.sqrt(np.sum(feature_axes * feature_axes, axis=1))
    sets = [signal_features(feature_axes[:, axis], sample_rate_hz) for axis in range(3)]
    sets.append(signal_features(magnitude, sample_rate_hz))
    return sets, means.tolist()


def append_feature_sets(row, prefixes, sets):
    for prefix, values in zip(prefixes, sets):
        for suffix, value in zip(FEATURE_SUFFIXES, values):
            row[f"{prefix}_{suffix}"] = value


def finalize_window(window, context, header, window_seconds):
    duration = window_seconds
    acc_rate = len(window.acc) / duration
    gyro_rate = len(window.gyro) / duration
    acc_sets, acc_means = vector_feature_sets(window.acc, acc_rate, True)
    gyro_sets, gyro_means = vector_feature_sets(window.gyro, gyro_rate, False)
    midpoint_ns = window.start_ns + (window.end_ns - window.start_ns) // 2
    utc_ms = context.anchor_utc_ms + (midpoint_ns - context.anchor_monotonic_ns) / 1_000_000.0
    elapsed_s = (window.start_ns - int(header["start_monotonic_ns"])) / 1_000_000_000.0

    row = {field: "" for field in CSV_FIELDS}
    row.update(
        time_iso=utc_iso(utc_ms),
        elapsed_s=elapsed_s,
        window_s=window_seconds,
        sample_count=len(window.acc),
        sample_rate_hz=acc_rate,
        x_mean=acc_means[0],
        y_mean=acc_means[1],
        z_mean=acc_means[2],
        gyro_sample_count=len(window.gyro),
        gyro_rate_hz=gyro_rate,
        gyro_x_mean=gyro_means[0],
        gyro_y_mean=gyro_means[1],
        gyro_z_mean=gyro_means[2],
        ride_mode=context.ride_mode,
        surface_type=context.surface_type,
        label_changed=int(window.label_changed),
    )
    append_feature_sets(row, ACC_PREFIXES, acc_sets)
    append_feature_sets(row, GYRO_PREFIXES, gyro_sets)

    if context.heart_rate_ns is not None:
        age = max(0.0, (window.end_ns - context.heart_rate_ns) / 1_000_000_000.0)
        row["heart_rate_age_s"] = age
        if age <= 5.0:
            row["heart_rate_bpm"] = context.heart_rate_bpm
    if context.wheel_ns is not None:
        age = max(0.0, (window.end_ns - context.wheel_ns) / 1_000_000_000.0)
        row["wheel_age_s"] = age
        row["wheel_revolutions_total"] = context.wheel_revolutions
        row["wheel_event_time_1024"] = context.wheel_event_time
        if age > 10.0:
            row["wheel_speed_kmh"] = 0.0
        elif context.wheel_speed_kmh is not None:
            row["wheel_speed_kmh"] = context.wheel_speed_kmh
    return row


def generate_features(input_path, output_path, window_seconds=1.0, row_callback=None):
    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")
    window_ns = int(round(window_seconds * 1_000_000_000))
    state = None
    window = None
    header = None
    rows_written = 0

    with contextlib.ExitStack() as stack:
        writer = None
        if output_path is not None:
            target = stack.enter_context(output_path.open("w", newline="", encoding="utf-8-sig"))
            writer = csv.DictWriter(target, fieldnames=CSV_FIELDS)
            writer.writeheader()

        def emit(row):
            nonlocal rows_written
            if writer is not None:
                writer.writerow(row)
            if row_callback is not None:
                row_callback(row)
            rows_written += 1

        for event_header, event_type, monotonic_ns, record in iter_records(input_path):
            if header is None:
                header = event_header
                start_ns = int(header["start_monotonic_ns"])
                window_index = max(0, (monotonic_ns - start_ns) // window_ns)
                first_window_start = start_ns + window_index * window_ns
                state = ContextState(
                    anchor_monotonic_ns=start_ns,
                    anchor_utc_ms=int(header["start_utc_ms"]),
                )
                window = WindowState(first_window_start, first_window_start + window_ns)

            while monotonic_ns >= window.end_ns:
                emit(finalize_window(window, state, header, window_seconds))
                window = WindowState(window.end_ns, window.end_ns + window_ns)

            if event_type == 1 and len(record) == 20:
                window.acc.append(struct.unpack_from(">fff", record, 8))
            elif event_type == 2 and len(record) == 20:
                window.gyro.append(struct.unpack_from(">fff", record, 8))
            elif event_type == 3 and len(record) == 10:
                state.heart_rate_bpm = struct.unpack_from(">H", record, 8)[0]
                state.heart_rate_ns = monotonic_ns
            elif event_type == 4 and len(record) == 18:
                revolutions, event_time, speed = struct.unpack_from(">IHf", record, 8)
                state.wheel_revolutions = revolutions
                state.wheel_event_time = event_time
                state.wheel_speed_kmh = None if math.isnan(speed) else float(speed)
                state.wheel_ns = monotonic_ns
            elif event_type == 5 and len(record) == 10:
                mode_code, surface_code = struct.unpack_from(">BB", record, 8)
                new_mode = RIDE_MODES.get(mode_code, f"unknown_{mode_code}")
                new_surface = SURFACES.get(surface_code, f"unknown_{surface_code}")
                had_label = state.ride_mode != "unknown" or state.surface_type != "unknown"
                if had_label and (new_mode != state.ride_mode or new_surface != state.surface_type):
                    window.label_changed = True
                state.ride_mode = new_mode
                state.surface_type = new_surface
            elif event_type == 6 and len(record) == 16:
                state.anchor_monotonic_ns = monotonic_ns
                state.anchor_utc_ms = struct.unpack_from(">q", record, 8)[0]

        if header is None:
            raise DecodeError("No records in input file")
        if window.acc or window.gyro:
            emit(finalize_window(window, state, header, window_seconds))

    return {
        "rows": rows_written,
        "columns": len(CSV_FIELDS),
        "output": str(output_path) if output_path is not None else "",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path, nargs="?")
    parser.add_argument("--window", type=float, default=1.0, help="window length in seconds")
    args = parser.parse_args()
    output = args.output or args.input.with_suffix(".features.csv")
    try:
        summary = generate_features(args.input, output, args.window)
    except (OSError, ValueError, DecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"rows={summary['rows']} columns={summary['columns']}")
    print(f"output={summary['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
