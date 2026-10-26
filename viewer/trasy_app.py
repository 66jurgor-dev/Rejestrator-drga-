from __future__ import annotations

import json
import csv
import ctypes
import io
import math
import os
import re
import sys
import uuid
import webbrowser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from threading import Timer

if getattr(sys, "frozen", False):
    if os.name == "nt" and os.environ.get("GPX_SHOW_CONSOLE") != "1":
        try:
            console_window = ctypes.windll.kernel32.GetConsoleWindow()
            if console_window:
                ctypes.windll.user32.ShowWindow(console_window, 0)
        except Exception:
            pass
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

SOURCE_DIR = Path(__file__).resolve().parent
BASE_DIR = Path(getattr(sys, "_MEIPASS", SOURCE_DIR))
if getattr(sys, "frozen", False):
    launched_path = Path(sys.argv[0]).resolve()
    APP_DIR = launched_path.parent if launched_path.suffix.lower() == ".exe" else Path(sys.executable).resolve().parent
else:
    APP_DIR = SOURCE_DIR
if os.environ.get("GPX_APP_DIR"):
    APP_DIR = Path(os.environ["GPX_APP_DIR"]).expanduser().resolve()
VENDOR_DIR = BASE_DIR / "vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

from flask import Flask, jsonify, render_template, request


GPX_NS = "http://www.topografix.com/GPX/1/1"
GPXNAV_NS = "https://local/gpxnav/1"
ET.register_namespace("", GPX_NS)
ET.register_namespace("gpxnav", GPXNAV_NS)

SURFACE_COLORS = {
    "asfalt": "#8a8a8a",
    "bita": "#ffe100",
    "asfalt/bita": "#ffe100",
    "szuter": "#ff9b00",
    "żwir": "#d9b928",
    "piach": "#ff00eb",
    "piasek": "#ff00eb",
    "ziemia": "#8b5a2b",
    "błoto": "#af7119",
    "trawa": "#55ff00",
    "korzenie": "#7b3f00",
    "kamyki": "#ff6e00",
    "kamyczki": "#ff6e00",
    "kamienie": "#ff0000",
    "bruk": "#8e44ad",
    "kostka": "#8e44ad",
    "płyty": "#607d8b",
    "skały": "#000000",
    "skaly": "#000000",
    "nieznana": "#7a8581",
}

SURFACE_LABELS = {
    "asfalt": "asfalt",
    "bita": "bita",
    "asfalt/bita": "bita",
    "szuter": "szuter",
    "żwir": "żwir",
    "piach": "piasek",
    "piasek": "piasek",
    "ziemia": "ziemia",
    "błoto": "bloto",
    "trawa": "trawa",
    "korzenie": "korzenie",
    "kamyki": "kamyki",
    "kamyczki": "kamyki",
    "kamienie": "kamienie",
    "bruk": "bruk",
    "kostka": "kostka",
    "płyty": "płyty",
    "skały": "skaly",
    "nieznana": "nieznana",
}

SURFACE_ALIASES = {
    "bita": "bita",
    "droga bita": "bita",
    "asfalt/bita": "bita",
    "asfalt bita": "bita",
    "asfalt-bita": "bita",
    "asfalt_bita": "bita",
    "zwir": "żwir",
    "żwir": "żwir",
    "zwirowa": "żwir",
    "żwirowa": "żwir",
    "piach": "piasek",
    "piasek": "piasek",
    "ziemna": "ziemia",
    "droga ziemna": "ziemia",
    "bloto": "bloto",
    "błoto": "bloto",
    "korzen": "korzenie",
    "korzeń": "korzenie",
    "korzenie": "korzenie",
    "kamyki": "kamyki",
    "kamyczki": "kamyki",
    "plyty": "płyty",
    "płyty": "płyty",
    "plyta": "płyty",
    "płyta": "płyty",
    "kamien": "kamienie",
    "kamień": "kamienie",
    "skaly": "skaly",
    "skała": "skaly",
    "skala": "skaly",
}

GPXNAV_DIR = APP_DIR / "GPXNAV"
CALORIE_BODY_MASS_KG = 83.0
GPXOLD_DIR = APP_DIR / "GPXOLD"
DOWNLOAD_DIR = APP_DIR / "Pobrane"
GPXNAV_DIR.mkdir(exist_ok=True)
GPXOLD_DIR.mkdir(exist_ok=True)
DOWNLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def safe_id(path: Path) -> str:
    return uuid.uuid5(uuid.NAMESPACE_URL, str(path.resolve())).hex


def route_name(path: Path, root: ET.Element) -> str:
    for element in root.iter():
        if local_name(element.tag) == "name" and element.text and element.text.strip():
            return element.text.strip()
    return path.stem


def gpxnav_source_name(path: Path, root: ET.Element) -> str:
    for element in root.iter():
        if (element.tag == f"{{{GPXNAV_NS}}}navigation" or local_name(element.tag) == "navigation") and element.attrib.get("source"):
            source = Path(element.attrib["source"]).name
            return source if source.lower().endswith(".gpx") else f"{Path(source).stem}.gpx"
    name = route_name(path, root)
    return f"{Path(name).stem}.gpx"


def parse_time(value: str) -> datetime | None:
    try:
        when = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return when.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def distance_km(first: dict, second: dict) -> float:
    phi1, phi2 = math.radians(first["lat"]), math.radians(second["lat"])
    dphi = phi2 - phi1
    dlambda = math.radians(second["lon"] - first["lon"])
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def calculate_active_calories(average_heart_rate: float, duration_seconds: int, body_mass_kg: float = CALORIE_BODY_MASS_KG) -> int:
    heart_rate_rest = 65.0
    heart_rate_max = 172.0
    vo2max = 35.0
    if duration_seconds <= 0 or body_mass_kg <= 0 or average_heart_rate <= 0:
        return 0
    intensity = (average_heart_rate - heart_rate_rest) / (heart_rate_max - heart_rate_rest)
    intensity = max(0.0, min(1.0, intensity))
    active_kcal = intensity * (vo2max - 3.5) * body_mass_kg * (duration_seconds / 60.0) * 0.005
    return int(math.floor(active_kcal + 0.5))


def route_stats(points: list[dict]) -> dict:
    distance = 0.0
    ascent = 0.0
    descent = 0.0
    previous = None
    for point in points:
        if previous is not None:
            distance += distance_km(previous, point)
            if previous.get("ele") is not None and point.get("ele") is not None:
                diff = point["ele"] - previous["ele"]
                if diff > 0:
                    ascent += diff
                elif diff < 0:
                    descent += abs(diff)
        previous = point

    times = [point["time"] for point in points if point.get("time") is not None]
    duration_seconds = 0
    if len(times) >= 2:
        duration_seconds = max(0, int((times[-1] - times[0]).total_seconds()))
    average_speed = distance / (duration_seconds / 3600) if duration_seconds > 0 else None
    heart_rate_points = [
        point for point in points
        if point.get("heart_rate_bpm") is not None and point.get("time") is not None
    ]
    average_heart_rate = None
    heart_rate_seconds = 0
    active_calories = None
    if heart_rate_points:
        average_heart_rate = sum(float(point["heart_rate_bpm"]) for point in heart_rate_points) / len(heart_rate_points)
        heart_rate_seconds = max(
            1,
            int((heart_rate_points[-1]["time"] - heart_rate_points[0]["time"]).total_seconds()) + 1,
        )
        active_calories = calculate_active_calories(average_heart_rate, heart_rate_seconds)
    return {
        "distance_km": round(distance, 2),
        "ascent_m": round(ascent),
        "descent_m": round(descent),
        "duration_seconds": duration_seconds,
        "average_speed_kmh": round(average_speed, 1) if average_speed is not None else None,
        "average_heart_rate_bpm": round(average_heart_rate, 1) if average_heart_rate is not None else None,
        "heart_rate_seconds": heart_rate_seconds,
        "active_calories_83kg": active_calories,
    }


def route_profile(points: list[dict]) -> list[dict]:
    profile = []
    distance = 0.0
    previous = None
    for point in points:
        angle = None
        if previous is not None:
            segment_km = distance_km(previous, point)
            distance += segment_km
            if previous.get("ele") is not None and point.get("ele") is not None and segment_km > 0:
                angle = math.degrees(math.atan2(point["ele"] - previous["ele"], segment_km * 1000))
        profile.append(
            {
                "km": round(distance, 4),
                "ele": round(point["ele"], 1) if point.get("ele") is not None else None,
                "angle": round(angle, 1) if angle is not None else None,
                "lat": point["lat"],
                "lon": point["lon"],
                "heart_rate_bpm": point.get("heart_rate_bpm"),
                "wheel_speed_kmh": point.get("wheel_speed_kmh"),
                "shake_score": point.get("shake_score"),
                "ride_mode": point.get("ride_mode"),
            }
        )
        previous = point
    return profile


def route_list_metadata(path: Path, points: list[dict]) -> dict:
    dated_points = [point["time"] for point in points if point.get("time") is not None]
    route_date = dated_points[0] if dated_points else None
    if route_date is None:
        filename_date = re.search(r"(?<!\d)(20\d{2})[-_]?(\d{2})[-_]?(\d{2})(?!\d)", path.stem)
        if filename_date:
            try:
                route_date = datetime(*(int(part) for part in filename_date.groups()), tzinfo=timezone.utc)
            except ValueError:
                route_date = None
    if route_date is None:
        route_date = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    return {
        "route_date": route_date.isoformat().replace("+00:00", "Z"),
        "route_timestamp": route_date.timestamp(),
        "has_full_telemetry": all(
            any(point.get(field) is not None for point in points)
            for field in ("heart_rate_bpm", "wheel_speed_kmh", "shake_score")
        ),
    }


def parse_gpxnav(path: Path) -> dict:
    root = ET.parse(path).getroot()
    points = []
    for element in root.iter():
        if local_name(element.tag) != "trkpt":
            continue
        try:
            point = {
                "lat": float(element.attrib["lat"]),
                "lon": float(element.attrib["lon"]),
                "ele": None,
                "time": None,
                "heart_rate_bpm": None,
                "wheel_speed_kmh": None,
                "shake_score": None,
                "ride_mode": None,
            }
            for child in element.iter():
                name = local_name(child.tag)
                if name == "ele" and child.text:
                    try:
                        point["ele"] = float(child.text.strip())
                    except ValueError:
                        point["ele"] = None
                elif name == "time" and child.text:
                    point["time"] = parse_time(child.text)
                elif name == "telemetry":
                    attrs = child.attrib
                    try:
                        point["heart_rate_bpm"] = float(attrs["heart_rate_bpm"]) if attrs.get("heart_rate_bpm") else None
                    except ValueError:
                        point["heart_rate_bpm"] = None
                    try:
                        point["wheel_speed_kmh"] = float(attrs["wheel_speed_kmh"]) if attrs.get("wheel_speed_kmh") else None
                    except ValueError:
                        point["wheel_speed_kmh"] = None
                    try:
                        point["shake_score"] = float(attrs["shake_score"]) if attrs.get("shake_score") else None
                    except ValueError:
                        point["shake_score"] = None
                    ride_mode = attrs.get("ride_mode")
                    point["ride_mode"] = ride_mode if ride_mode in {"jazda", "prowadzenie"} else None
            points.append(point)
        except (KeyError, ValueError):
            continue
    if len(points) < 2:
        raise ValueError("Plik nie zawiera poprawnej trasy.")

    segments = []
    for element in root.iter():
        if element.tag == f"{{{GPXNAV_NS}}}segment" or local_name(element.tag) == "segment":
            attrs = element.attrib
            if "type" in attrs and "from_km" in attrs and "to_km" in attrs:
                segments.append(
                    {
                        "type": attrs.get("type", ""),
                        "label": attrs.get("label") or attrs.get("type", ""),
                        "from_km": attrs.get("from_km", ""),
                        "to_km": attrs.get("to_km", ""),
                        "color": attrs.get("color", ""),
                    }
                )

    return {
        "id": safe_id(path),
        "kind": "gpxnav",
        "name": route_name(path, root),
        "display_name": path.name,
        "gpx_file": gpxnav_source_name(path, root),
        "file": path.name,
        "points": [[point["lat"], point["lon"]] for point in points],
        "stats": route_stats(points),
        "profile": route_profile(points),
        "segments": segments,
        "waypoints": gpxnav_waypoints(root),
        **route_list_metadata(path, points),
    }


def parse_waypoints(root: ET.Element) -> list[dict]:
    waypoints = []
    for element in root.iter():
        if local_name(element.tag) != "wpt":
            continue
        try:
            waypoint = {
                "lat": float(element.attrib["lat"]),
                "lon": float(element.attrib["lon"]),
                "name": "",
                "description": "",
                "comment": "",
                "symbol": "",
                "type": "",
                "ele": None,
                "time": None,
            }
        except (KeyError, ValueError):
            continue
        for child in element:
            name = local_name(child.tag)
            text = child.text.strip() if child.text else ""
            if name == "name":
                waypoint["name"] = text
            elif name == "desc":
                waypoint["description"] = text
            elif name == "cmt":
                waypoint["comment"] = text
            elif name == "sym":
                waypoint["symbol"] = text
            elif name == "type":
                waypoint["type"] = text
            elif name == "ele" and text:
                try:
                    waypoint["ele"] = float(text)
                except ValueError:
                    pass
            elif name == "time" and text:
                parsed_time = parse_time(text)
                waypoint["time"] = parsed_time.isoformat().replace("+00:00", "Z") if parsed_time else None
        waypoints.append(waypoint)
    return waypoints


@lru_cache(maxsize=128)
def find_source_gpx(source_name: str) -> Path | None:
    if not source_name or Path(source_name).name != source_name:
        return None
    search_roots = [APP_DIR.parent / "Dane z tras", APP_DIR / "GPXOLD"]
    for search_root in search_roots:
        if not search_root.exists():
            continue
        for candidate in search_root.rglob(source_name):
            if candidate.is_file():
                return candidate
    return None


def gpxnav_waypoints(root: ET.Element, source_root: Path | None = None) -> list[dict]:
    embedded = parse_waypoints(root)
    if embedded:
        return embedded
    source_name = ""
    for element in root.iter():
        if local_name(element.tag) == "navigation":
            source_name = Path(element.attrib.get("source", "")).name
            break
    if not source_name:
        return []
    if source_root is None:
        source_path = find_source_gpx(source_name)
    else:
        matches = [candidate for candidate in source_root.rglob(source_name) if candidate.is_file()]
        source_path = matches[0] if matches else None
    if source_path is None:
        return []
    try:
        return parse_waypoints(ET.parse(source_path).getroot())
    except (ET.ParseError, OSError):
        return []


def parse_plain_gpx(path: Path) -> dict:
    root = ET.parse(path).getroot()
    points = []
    for element in root.iter():
        if local_name(element.tag) != "trkpt":
            continue
        try:
            point = {"lat": float(element.attrib["lat"]), "lon": float(element.attrib["lon"]), "ele": None, "time": None}
            for child in element:
                name = local_name(child.tag)
                if name == "ele" and child.text:
                    try:
                        point["ele"] = float(child.text.strip())
                    except ValueError:
                        point["ele"] = None
                elif name == "time" and child.text:
                    point["time"] = parse_time(child.text)
            points.append(point)
        except (KeyError, ValueError):
            continue
    if len(points) < 2:
        raise ValueError("Plik nie zawiera poprawnej trasy.")

    return {
        "id": safe_id(path),
        "kind": "gpxold",
        "name": route_name(path, root),
        "display_name": path.name,
        "gpx_file": path.name,
        "file": path.name,
        "points": [[point["lat"], point["lon"]] for point in points],
        "stats": route_stats(points),
        "profile": route_profile(points),
        "segments": [],
        "waypoints": parse_waypoints(root),
        **route_list_metadata(path, points),
    }


def list_routes() -> list[dict]:
    routes = []
    for path in sorted(GPXNAV_DIR.glob("*.gpxnav"), key=lambda item: item.name.lower()):
        try:
            routes.append(parse_gpxnav(path))
        except (ET.ParseError, OSError, ValueError) as error:
            routes.append(
                {
                    "id": safe_id(path),
                    "kind": "gpxnav",
                    "name": path.stem,
                    "display_name": path.name,
                    "file": path.name,
                    "points": [],
                    "segments": [],
                    "error": str(error),
                }
            )
    for path in sorted(GPXOLD_DIR.glob("*.gpx"), key=lambda item: item.name.lower()):
        try:
            routes.append(parse_plain_gpx(path))
        except (ET.ParseError, OSError, ValueError) as error:
            routes.append(
                {
                    "id": safe_id(path),
                    "kind": "gpxold",
                    "name": path.stem,
                    "display_name": path.name,
                    "gpx_file": path.name,
                    "file": path.name,
                    "points": [],
                    "segments": [],
                    "error": str(error),
                }
            )
    return sorted(routes, key=lambda route: route.get("route_timestamp", 0), reverse=True)


def summary_stats(routes: list[dict]) -> dict:
    distance = 0.0
    ascent = 0.0
    duration = 0
    counted = 0
    for route in routes:
        if route.get("error"):
            continue
        stats = route.get("stats") or {}
        distance += float(stats.get("distance_km") or 0)
        ascent += float(stats.get("ascent_m") or 0)
        duration += int(stats.get("duration_seconds") or 0)
        counted += 1
    average_speed = distance / (duration / 3600) if duration > 0 else None
    average_distance = distance / counted if counted > 0 else None
    average_duration = duration / counted if counted > 0 else None
    return {
        "routes": counted,
        "distance_km": round(distance, 2),
        "ascent_m": round(ascent),
        "duration_seconds": duration,
        "average_distance_km": round(average_distance, 2) if average_distance is not None else None,
        "average_duration_seconds": round(average_duration) if average_duration is not None else None,
        "average_speed_kmh": round(average_speed, 1) if average_speed is not None else None,
    }


def find_route_file(route_id: str) -> Path:
    for path in list(GPXNAV_DIR.glob("*.gpxnav")) + list(GPXOLD_DIR.glob("*.gpx")):
        if safe_id(path) == route_id:
            return path
    raise FileNotFoundError("Nie znaleziono wybranej trasy.")


def unique_output_path(name: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_. -]+", "_", name).strip(" ._") or "trasa"
    if not safe_name.lower().endswith(".gpx"):
        safe_name += ".gpx"
    candidate = DOWNLOAD_DIR / safe_name
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for number in range(2, 10000):
        next_candidate = DOWNLOAD_DIR / f"{stem}_{number}{suffix}"
        if not next_candidate.exists():
            return next_candidate
    raise OSError("Nie udało się utworzyć unikalnej nazwy pliku.")


def unique_csv_output_path(name: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_. -]+", "_", Path(name).stem).strip(" ._") or "polaczone_dane"
    candidate = DOWNLOAD_DIR / f"{safe_name}_sieci_neuronowe.csv"
    if not candidate.exists():
        return candidate
    for number in range(2, 10000):
        next_candidate = DOWNLOAD_DIR / f"{safe_name}_sieci_neuronowe_{number}.csv"
        if not next_candidate.exists():
            return next_candidate
    raise OSError("Nie udało się utworzyć unikalnej nazwy pliku CSV.")


def unique_gpxnav_output_path(name: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_. -]+", "_", Path(name).stem).strip(" ._") or "trasa"
    candidate = GPXNAV_DIR / f"{safe_name}.gpxnav"
    if not candidate.exists():
        return candidate
    for number in range(2, 10000):
        next_candidate = GPXNAV_DIR / f"{safe_name}_{number}.gpxnav"
        if not next_candidate.exists():
            return next_candidate
    raise OSError("Nie udało się utworzyć unikalnej nazwy pliku GPXNAV.")


def parse_uploaded_gpx(file_storage) -> list[dict]:
    file_storage.stream.seek(0)
    root = ET.parse(file_storage.stream).getroot()
    points = []
    for element in root.iter():
        if local_name(element.tag) != "trkpt":
            continue
        try:
            point = {"lat": float(element.attrib["lat"]), "lon": float(element.attrib["lon"]), "ele": None, "time": None}
        except (KeyError, ValueError):
            continue
        for child in element:
            name = local_name(child.tag)
            if name == "ele" and child.text:
                try:
                    point["ele"] = float(child.text.strip())
                except ValueError:
                    point["ele"] = None
            elif name == "time" and child.text:
                point["time"] = parse_time(child.text)
        if point["time"] is not None:
            points.append(point)
    points.sort(key=lambda item: item["time"])
    if len(points) < 2:
        raise ValueError("Plik GPX musi zawierać co najmniej dwa punkty trasy z czasem.")
    distance = 0.0
    previous = None
    for point in points:
        if previous is not None:
            distance += distance_km(previous, point)
        point["distance_km"] = distance
        previous = point
    return points


def parse_uploaded_vibration_csv(file_storage) -> tuple[list[str], list[dict]]:
    file_storage.stream.seek(0)
    text = file_storage.stream.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("Plik CSV nie ma nagłówka.")
    if "time_iso" not in reader.fieldnames:
        raise ValueError("Plik CSV musi zawierać kolumnę time_iso.")
    rows = []
    for row in reader:
        when = parse_time(row.get("time_iso", ""))
        if when is None:
            continue
        row["_time"] = when
        rows.append(row)
    rows.sort(key=lambda item: item["_time"])
    if not rows:
        raise ValueError("Plik CSV nie zawiera poprawnych rekordów z czasem time_iso.")
    return list(reader.fieldnames), rows


def interpolate_gpx(points: list[dict], when: datetime, start_index: int) -> tuple[dict | None, int]:
    if when < points[0]["time"] or when > points[-1]["time"]:
        return None, start_index
    index = max(0, min(start_index, len(points) - 2))
    while index < len(points) - 2 and points[index + 1]["time"] < when:
        index += 1
    while index > 0 and points[index]["time"] > when:
        index -= 1
    first = points[index]
    second = points[index + 1]
    span = (second["time"] - first["time"]).total_seconds()
    ratio = 0.0 if span <= 0 else (when - first["time"]).total_seconds() / span
    ratio = max(0.0, min(1.0, ratio))
    segment_km = distance_km(first, second)
    ele = None
    grade_percent = None
    slope_angle = None
    if first.get("ele") is not None and second.get("ele") is not None:
        ele = first["ele"] + (second["ele"] - first["ele"]) * ratio
        if segment_km > 0:
            ele_diff = second["ele"] - first["ele"]
            grade_percent = (ele_diff / (segment_km * 1000)) * 100
            slope_angle = math.degrees(math.atan2(ele_diff, segment_km * 1000))
    speed = segment_km / (span / 3600) if span > 0 else None
    return {
        "gpx_lat": first["lat"] + (second["lat"] - first["lat"]) * ratio,
        "gpx_lon": first["lon"] + (second["lon"] - first["lon"]) * ratio,
        "gpx_ele_m": ele,
        "gpx_distance_km": first["distance_km"] + segment_km * ratio,
        "gpx_speed_kmh": speed,
        "gpx_grade_percent": grade_percent,
        "gpx_slope_angle_deg": slope_angle,
    }, index


def fmt_number(value: float | None, digits: int = 6) -> str:
    if value is None or not NumberLike(value):
        return ""
    return f"{float(value):.{digits}f}"


def NumberLike(value) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def surface_key(value: str | None) -> str:
    normalized = (value or "nieznana").strip().lower() or "nieznana"
    return SURFACE_ALIASES.get(normalized, normalized)


def surface_label(value: str) -> str:
    key = surface_key(value)
    return SURFACE_LABELS.get(key, value or "nieznana")


def build_surface_segments(records: list[dict], route_end_km: float) -> list[dict]:
    if not records:
        return []
    segments = []
    current_type = surface_key(records[0].get("surface_type"))
    start_km = float(records[0]["gpx_distance_km"])
    previous_km = start_km
    for record in records[1:]:
        record_type = surface_key(record.get("surface_type"))
        km = float(record["gpx_distance_km"])
        if record_type != current_type:
            if previous_km > start_km:
                segments.append({"type": current_type, "from_km": start_km, "to_km": previous_km})
            current_type = record_type
            start_km = previous_km
        previous_km = km
    end_km = max(previous_km, route_end_km)
    if end_km > start_km:
        segments.append({"type": current_type, "from_km": start_km, "to_km": end_km})
    return segments


def write_gpxnav_from_merge(gpx_points: list[dict], records: list[dict], output_path: Path, source_name: str) -> int:
    root = ET.Element(
        f"{{{GPX_NS}}}gpx",
        {
            "version": "1.1",
            "creator": "GPXtrasy_naw",
        },
    )
    metadata = ET.SubElement(root, f"{{{GPX_NS}}}metadata")
    name_element = ET.SubElement(metadata, f"{{{GPX_NS}}}name")
    name_element.text = Path(output_path).stem
    navigation = ET.SubElement(metadata, f"{{{GPXNAV_NS}}}navigation", {"source": Path(source_name).name})
    route_end_km = gpx_points[-1].get("distance_km") or 0.0
    for segment in build_surface_segments(records, route_end_km):
        kind = surface_key(segment["type"])
        ET.SubElement(
            navigation,
            f"{{{GPXNAV_NS}}}segment",
            {
                "type": kind,
                "label": surface_label(kind),
                "from_km": f"{segment['from_km']:.5f}",
                "to_km": f"{segment['to_km']:.5f}",
                "color": SURFACE_COLORS.get(kind, "#7a8581"),
            },
        )

    track = ET.SubElement(root, f"{{{GPX_NS}}}trk")
    track_name = ET.SubElement(track, f"{{{GPX_NS}}}name")
    track_name.text = Path(output_path).stem
    track_segment = ET.SubElement(track, f"{{{GPX_NS}}}trkseg")
    for point in gpx_points:
        trkpt = ET.SubElement(
            track_segment,
            f"{{{GPX_NS}}}trkpt",
            {"lat": f"{point['lat']:.8f}", "lon": f"{point['lon']:.8f}"},
        )
        if point.get("ele") is not None:
            ET.SubElement(trkpt, f"{{{GPX_NS}}}ele").text = f"{point['ele']:.2f}"
        if point.get("time") is not None:
            ET.SubElement(trkpt, f"{{{GPX_NS}}}time").text = point["time"].isoformat().replace("+00:00", "Z")

    ET.indent(root, space="  ")
    ET.ElementTree(root).write(output_path, encoding="utf-8", xml_declaration=True)
    return len(navigation)


def merge_gpx_and_csv(gpx_file, csv_file) -> dict:
    gpx_points = parse_uploaded_gpx(gpx_file)
    csv_fields, csv_rows = parse_uploaded_vibration_csv(csv_file)
    output_path = unique_csv_output_path(csv_file.filename or "drgania.csv")
    gpxnav_path = unique_gpxnav_output_path(gpx_file.filename or "trasa.gpx")
    added_fields = [
        "gpx_lat",
        "gpx_lon",
        "gpx_ele_m",
        "gpx_distance_km",
        "gpx_speed_kmh",
        "gpx_grade_percent",
        "gpx_slope_angle_deg",
    ]
    matched = 0
    skipped = 0
    segment_index = 0
    matched_records = []
    with output_path.open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.DictWriter(output, fieldnames=csv_fields + added_fields, delimiter=";")
        writer.writeheader()
        for row in csv_rows:
            interpolation, segment_index = interpolate_gpx(gpx_points, row["_time"], segment_index)
            if interpolation is None:
                skipped += 1
                continue
            out_row = {field: row.get(field, "") for field in csv_fields}
            out_row.update(
                {
                    "gpx_lat": fmt_number(interpolation["gpx_lat"], 8),
                    "gpx_lon": fmt_number(interpolation["gpx_lon"], 8),
                    "gpx_ele_m": fmt_number(interpolation["gpx_ele_m"], 2),
                    "gpx_distance_km": fmt_number(interpolation["gpx_distance_km"], 5),
                    "gpx_speed_kmh": fmt_number(interpolation["gpx_speed_kmh"], 3),
                    "gpx_grade_percent": fmt_number(interpolation["gpx_grade_percent"], 3),
                    "gpx_slope_angle_deg": fmt_number(interpolation["gpx_slope_angle_deg"], 3),
                }
            )
            writer.writerow(out_row)
            matched_records.append(
                {
                    "surface_type": out_row.get("surface_type") or out_row.get("typ_nawierzchni") or out_row.get("surface") or "",
                    "gpx_distance_km": interpolation["gpx_distance_km"],
                }
            )
            matched += 1
    segment_count = write_gpxnav_from_merge(gpx_points, matched_records, gpxnav_path, gpx_file.filename or "trasa.gpx")
    return {
        "path": str(output_path),
        "file": output_path.name,
        "csv_path": str(output_path),
        "csv_file": output_path.name,
        "gpxnav_path": str(gpxnav_path),
        "gpxnav_file": gpxnav_path.name,
        "gpxnav_segments": segment_count,
        "matched_rows": matched,
        "skipped_rows": skipped,
        "gpx_points": len(gpx_points),
        "csv_rows": len(csv_rows),
    }


def export_plain_gpx(source_path: Path, output_path: Path) -> dict:
    source_root = ET.parse(source_path).getroot()
    name = route_name(source_path, source_root)
    source_name = gpxnav_source_name(source_path, source_root)
    root = ET.Element(
        f"{{{GPX_NS}}}gpx",
        {
            "version": "1.1",
            "creator": "GPXtrasy_naw",
        },
    )
    metadata = ET.SubElement(root, f"{{{GPX_NS}}}metadata")
    name_element = ET.SubElement(metadata, f"{{{GPX_NS}}}name")
    name_element.text = name
    time_element = ET.SubElement(metadata, f"{{{GPX_NS}}}time")
    time_element.text = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    track = ET.SubElement(root, f"{{{GPX_NS}}}trk")
    track_name = ET.SubElement(track, f"{{{GPX_NS}}}name")
    track_name.text = name
    track_segment = ET.SubElement(track, f"{{{GPX_NS}}}trkseg")

    point_count = 0
    for source_point in source_root.iter():
        if local_name(source_point.tag) != "trkpt":
            continue
        if "lat" not in source_point.attrib or "lon" not in source_point.attrib:
            continue
        point = ET.SubElement(
            track_segment,
            f"{{{GPX_NS}}}trkpt",
            {"lat": source_point.attrib["lat"], "lon": source_point.attrib["lon"]},
        )
        for child in source_point:
            child_name = local_name(child.tag)
            if child_name in {"ele", "time"} and child.text:
                copied = ET.SubElement(point, f"{{{GPX_NS}}}{child_name}")
                copied.text = child.text.strip()
        point_count += 1

    if point_count < 2:
        raise ValueError("Wybrany plik GPXNAV nie zawiera poprawnej trasy.")

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    return {"name": name, "source_name": source_name, "points": point_count}


@app.get("/")
def index():
    return render_template("trasy.html")


@app.get("/api/info")
def info_api():
    return jsonify(
        app_dir=str(APP_DIR),
        gpxnav_dir=str(GPXNAV_DIR),
        gpxnav_files=sorted(path.name for path in GPXNAV_DIR.glob("*.gpxnav")),
    )


@app.get("/api/routes")
def routes_api():
    routes = list_routes()
    return jsonify(
        routes=routes,
        summary=summary_stats(routes),
        gpxnav_dir=str(GPXNAV_DIR),
        gpxold_dir=str(GPXOLD_DIR),
        download_dir=str(DOWNLOAD_DIR),
    )


@app.post("/api/download/<route_id>")
def download_route(route_id: str):
    try:
        source_path = find_route_file(route_id)
        if source_path.suffix.lower() == ".gpxnav":
            source_root = ET.parse(source_path).getroot()
            output_path = unique_output_path(gpxnav_source_name(source_path, source_root))
        else:
            output_path = unique_output_path(source_path.name)
        stats = export_plain_gpx(source_path, output_path)
        return jsonify(path=str(output_path), file=output_path.name, points=stats["points"], name=stats["name"])
    except (ET.ParseError, OSError, ValueError, FileNotFoundError) as error:
        return jsonify(error=str(error)), 400


@app.post("/api/merge-gpx-csv")
def merge_gpx_csv_api():
    try:
        gpx_file = request.files.get("gpx")
        csv_file = request.files.get("csv")
        if gpx_file is None or not gpx_file.filename:
            raise ValueError("Wybierz plik GPX.")
        if csv_file is None or not csv_file.filename:
            raise ValueError("Wybierz plik CSV z drganiami.")
        result = merge_gpx_and_csv(gpx_file, csv_file)
        return jsonify(result)
    except (ET.ParseError, UnicodeDecodeError, OSError, ValueError) as error:
        return jsonify(error=str(error)), 400


if __name__ == "__main__":
    port = int(os.environ.get("GPX_PORT", "5020"))
    address = f"http://127.0.0.1:{port}"
    if os.environ.get("GPX_NO_BROWSER") != "1":
        Timer(1.25, lambda: webbrowser.open(address)).start()
    app.run(host="127.0.0.1", port=port, debug=False, threaded=False)
