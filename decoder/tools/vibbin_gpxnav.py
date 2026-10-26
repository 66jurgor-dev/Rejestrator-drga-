#!/usr/bin/env python3
"""Create a lightweight GPXNAV file from a VIBRAW BIN and a timed GPX track."""

from __future__ import annotations

import argparse
import bisect
import datetime as dt
import math
import pathlib
import sys
import xml.etree.ElementTree as ET

from vibbin_decoder import DecodeError, decode_file
from vibbin_features import generate_features


GPX_NS = "http://www.topografix.com/GPX/1/1"
GPXNAV_NS = "https://local/gpxnav/1"
ET.register_namespace("", GPX_NS)
ET.register_namespace("gpxnav", GPXNAV_NS)

# Fixed across routes. A raw value of 1 rad/s maps to shake_score 50.
SHAKE_HALF_SCALE_RAD_S = 1.0

SURFACE_LABELS = {
    "twarda": "Twarda",
    "stabilna_nat": "Stabilna NAT",
    "nierownosci_stab": "Nierownosci STAB",
    "ruchoma_drob": "Ruchoma DROB",
    "ruchoma_grub": "Ruchoma GRUB",
    "rynna": "Rynna",
    "miekkie": "Miekkie",
    "regularne_twar": "Regularne TWAR",
    "brak": "BRAK",
    "unknown": "BRAK",
}

SURFACE_COLORS = {
    "twarda": "#777777",
    "stabilna_nat": "#58A84B",
    "nierownosci_stab": "#F2CF18",
    "ruchoma_drob": "#F58B24",
    "ruchoma_grub": "#DF2F2F",
    "rynna": "#2F5E8E",
    "miekkie": "#7A4A24",
    "regularne_twar": "#9DAA55",
    "brak": "#111111",
    "unknown": "#111111",
}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_time(value: str) -> dt.datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def haversine_km(a: dict, b: dict) -> float:
    radius_km = 6371.0088
    lat1 = math.radians(a["lat"])
    lat2 = math.radians(b["lat"])
    dlat = lat2 - lat1
    dlon = math.radians(b["lon"] - a["lon"])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(value))


def read_gpx(path: pathlib.Path) -> tuple[str, list[dict]]:
    root = ET.parse(path).getroot()
    name = path.stem
    for element in root.iter():
        if local_name(element.tag) == "name" and element.text:
            name = element.text.strip()
            break

    points = []
    distance_km = 0.0
    previous = None
    for element in root.iter():
        if local_name(element.tag) != "trkpt":
            continue
        try:
            point = {
                "lat": float(element.attrib["lat"]),
                "lon": float(element.attrib["lon"]),
                "ele": None,
                "time": None,
            }
        except (KeyError, ValueError):
            continue
        for child in element:
            child_name = local_name(child.tag)
            if child_name == "ele" and child.text:
                try:
                    point["ele"] = float(child.text.strip())
                except ValueError:
                    pass
            elif child_name == "time" and child.text:
                point["time"] = parse_time(child.text)
        if point["time"] is None:
            raise ValueError("Kazdy punkt GPX musi zawierac czas.")
        if previous is not None:
            distance_km += haversine_km(previous, point)
        point["distance_km"] = distance_km
        point["utc_ms"] = point["time"].timestamp() * 1000.0
        points.append(point)
        previous = point

    if len(points) < 2:
        raise ValueError("Plik GPX nie zawiera co najmniej dwoch punktow trasy z czasem.")
    return name, points


def collect_vibraw_data(bin_path: pathlib.Path) -> tuple[dict, list[tuple], list[tuple], list[tuple]]:
    heart_rates = []
    wheel_speeds = []
    ride_modes = []

    def collect(row: dict) -> None:
        utc_ms = float(row["utc_ms"])
        if row["event_type"] == "HEART_RATE" and row["heart_rate_bpm"]:
            heart_rates.append((utc_ms, int(row["heart_rate_bpm"])))
        elif row["event_type"] == "WHEEL" and row["wheel_speed_kmh"]:
            wheel_speeds.append((utc_ms, float(row["wheel_speed_kmh"])))
        elif row["event_type"] == "LABEL":
            ride_modes.append((utc_ms, row["ride_mode"]))

    summary = decode_file(bin_path, None, collect)
    return summary, heart_rates, wheel_speeds, ride_modes


def latest_value(samples: list[tuple], times: list[float], utc_ms: float, max_age_ms: float):
    index = bisect.bisect_right(times, utc_ms) - 1
    if index < 0 or utc_ms - samples[index][0] > max_age_ms:
        return None
    return samples[index][1]


def nearest_value(samples: list[tuple], times: list[float], utc_ms: float, max_distance_ms: float):
    if not samples:
        return None
    right = bisect.bisect_left(times, utc_ms)
    candidates = []
    if right < len(samples):
        candidates.append(samples[right])
    if right > 0:
        candidates.append(samples[right - 1])
    selected = min(candidates, key=lambda sample: abs(sample[0] - utc_ms))
    return selected[1] if abs(selected[0] - utc_ms) <= max_distance_ms else None


def normalize_shake(raw_value: float) -> float:
    value = max(0.0, float(raw_value))
    return 100.0 * value / (value + SHAKE_HALF_SCALE_RAD_S)


def collect_shake_scores(bin_path: pathlib.Path) -> tuple[dict, list[tuple]]:
    scores = []

    def collect(row: dict) -> None:
        raw = 0.6 * float(row["gyro_3d_p95_abs"]) + 0.4 * float(row["gyro_3d_max_abs_delta"])
        utc_ms = parse_time(row["time_iso"]).timestamp() * 1000.0
        scores.append((utc_ms, normalize_shake(raw)))

    summary = generate_features(bin_path, None, 1.0, collect)
    return summary, scores


def generate_gpxnav(bin_path: pathlib.Path, gpx_path: pathlib.Path, output_path: pathlib.Path) -> dict:
    track_name, points = read_gpx(gpx_path)
    bin_summary, heart_rates, wheel_speeds, ride_modes = collect_vibraw_data(bin_path)
    feature_summary, shake_scores = collect_shake_scores(bin_path)
    heart_times = [sample[0] for sample in heart_rates]
    wheel_times = [sample[0] for sample in wheel_speeds]
    ride_mode_times = [sample[0] for sample in ride_modes]
    shake_times = [sample[0] for sample in shake_scores]

    telemetry_points = 0
    for point in points:
        point["heart_rate_bpm"] = latest_value(heart_rates, heart_times, point["utc_ms"], 15_000)
        point["wheel_speed_kmh"] = latest_value(wheel_speeds, wheel_times, point["utc_ms"], 5_000)
        point["ride_mode"] = latest_value(ride_modes, ride_mode_times, point["utc_ms"], float("inf"))
        point["shake_score"] = nearest_value(shake_scores, shake_times, point["utc_ms"], 1_500)
        if any(point[key] is not None for key in ("heart_rate_bpm", "wheel_speed_kmh", "shake_score")):
            telemetry_points += 1

    root = ET.Element(f"{{{GPX_NS}}}gpx", {"version": "1.1", "creator": "VIBRAW_Dekoder"})
    metadata = ET.SubElement(root, f"{{{GPX_NS}}}metadata")
    ET.SubElement(metadata, f"{{{GPX_NS}}}name").text = track_name
    navigation = ET.SubElement(
        metadata,
        f"{{{GPXNAV_NS}}}navigation",
        {
            "format": "gpxnav",
            "version": "2",
            "source": gpx_path.name,
            "surface_metric": "shake_score",
            "shake_window_s": "1.0",
        },
    )

    track = ET.SubElement(root, f"{{{GPX_NS}}}trk")
    ET.SubElement(track, f"{{{GPX_NS}}}name").text = track_name
    track_segment = ET.SubElement(track, f"{{{GPX_NS}}}trkseg")
    for point in points:
        trkpt = ET.SubElement(
            track_segment,
            f"{{{GPX_NS}}}trkpt",
            {"lat": f"{point['lat']:.8f}", "lon": f"{point['lon']:.8f}"},
        )
        if point["ele"] is not None:
            ET.SubElement(trkpt, f"{{{GPX_NS}}}ele").text = f"{point['ele']:.2f}"
        ET.SubElement(trkpt, f"{{{GPX_NS}}}time").text = point["time"].isoformat().replace("+00:00", "Z")
        telemetry = {}
        if point["heart_rate_bpm"] is not None:
            telemetry["heart_rate_bpm"] = str(point["heart_rate_bpm"])
        if point["wheel_speed_kmh"] is not None:
            telemetry["wheel_speed_kmh"] = f"{point['wheel_speed_kmh']:.3f}"
        if point["shake_score"] is not None:
            telemetry["shake_score"] = f"{point['shake_score']:.3f}"
        if point["ride_mode"] in {"jazda", "prowadzenie"}:
            telemetry["ride_mode"] = point["ride_mode"]
        if telemetry:
            extensions = ET.SubElement(trkpt, f"{{{GPX_NS}}}extensions")
            ET.SubElement(extensions, f"{{{GPXNAV_NS}}}telemetry", telemetry)

    ET.indent(root, space="  ")
    ET.ElementTree(root).write(output_path, encoding="utf-8", xml_declaration=True)
    return {
        "points": len(points),
        "segments": 0,
        "telemetry_points": telemetry_points,
        "shake_windows": feature_summary["rows"],
        "heart_rate_samples": len(heart_rates),
        "wheel_samples": len(wheel_speeds),
        "bin_events": bin_summary["events"],
        "output": str(output_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bin", type=pathlib.Path, help="input VIBRAW BIN")
    parser.add_argument("gpx", type=pathlib.Path, help="timed GPX track")
    parser.add_argument("output", type=pathlib.Path, nargs="?", help="output GPXNAV")
    args = parser.parse_args()
    output = args.output or args.bin.with_suffix(".gpxnav")
    try:
        summary = generate_gpxnav(args.bin, args.gpx, output)
    except (OSError, ValueError, ET.ParseError, DecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"points={summary['points']} shake_windows={summary['shake_windows']}")
    print(f"heart_rate_samples={summary['heart_rate_samples']} wheel_samples={summary['wheel_samples']}")
    print(f"output={summary['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
