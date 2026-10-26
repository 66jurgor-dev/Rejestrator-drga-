from __future__ import annotations

import math
import statistics
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def haversine_km(a: dict, b: dict) -> float:
    radius = 6371.0088
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat = lat2 - lat1
    dlon = math.radians(b["lon"] - a["lon"])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(value))


def read_profile(path: Path) -> list[dict]:
    root = ET.parse(path).getroot()
    profile = []
    distance = 0.0
    previous = None
    for element in root.iter():
        if local_name(element.tag) != "trkpt":
            continue
        point = {"lat": float(element.attrib["lat"]), "lon": float(element.attrib["lon"]), "ele": None,
                 "wheelSpeed": None, "shakeScore": None}
        for child in element.iter():
            name = local_name(child.tag)
            if name == "ele" and child.text:
                point["ele"] = float(child.text)
            elif name == "telemetry":
                if child.attrib.get("wheel_speed_kmh"):
                    point["wheelSpeed"] = float(child.attrib["wheel_speed_kmh"])
                if child.attrib.get("shake_score"):
                    point["shakeScore"] = float(child.attrib["shake_score"])
        if previous is not None:
            distance += haversine_km(previous, point)
        point["km"] = distance
        if point["ele"] is not None:
            profile.append(point)
        previous = point
    return profile


def interpolate(profile: list[dict], km: float) -> float:
    if km <= profile[0]["km"]:
        return profile[0]["ele"]
    if km >= profile[-1]["km"]:
        return profile[-1]["ele"]
    low, high = 0, len(profile) - 1
    while low < high:
        middle = (low + high) // 2
        if profile[middle]["km"] < km:
            low = middle + 1
        else:
            high = middle
    before, after = profile[low - 1], profile[low]
    ratio = (km - before["km"]) / (after["km"] - before["km"] or 1)
    return before["ele"] + (after["ele"] - before["ele"]) * ratio


def kind(grade: float) -> str:
    return "up" if grade > 2 else ("down" if grade < -2 else "flat")


def refresh(segment: dict) -> dict:
    segment["lengthKm"] = segment["toKm"] - segment["fromKm"]
    segment["grade"] = (segment["endEle"] - segment["startEle"]) / (segment["lengthKm"] * 10)
    segment["kind"] = kind(segment["grade"])
    return segment


def merge(left: dict, right: dict) -> dict:
    return refresh({"fromKm": left["fromKm"], "toKm": right["toKm"],
                    "startEle": left["startEle"], "endEle": right["endEle"]})


def merge_short(segments: list[dict], minimum: float = 0.5) -> list[dict]:
    result = list(segments)
    protected: set[int] = set()
    while len(result) > 1:
        index = next((i for i, segment in enumerate(result)
                      if segment["lengthKm"] + 1e-6 < minimum and i not in protected), -1)
        if index < 0:
            break
        current = result[index]
        left = result[index - 1] if index > 0 else None
        right = result[index + 1] if index < len(result) - 1 else None

        def compatible(neighbor: dict | None) -> bool:
            if neighbor is None:
                return False
            if {current["kind"], neighbor["kind"]} == {"up", "down"}:
                return False
            return current["kind"] == neighbor["kind"] or "flat" in {current["kind"], neighbor["kind"]}

        can_left, can_right = compatible(left), compatible(right)
        if (current["kind"] == "flat" and left and right and
                {left["kind"], right["kind"]} == {"up", "down"}):
            protected.add(index)
            continue
        if not can_left and not can_right:
            protected.add(index)
            continue
        if index == 0:
            result[0:2] = [merge(result[0], result[1])]
        elif index == len(result) - 1:
            result[index - 1:index + 1] = [merge(result[index - 1], result[index])]
        elif not can_left:
            result[index:index + 2] = [merge(current, right)]
        elif not can_right:
            result[index - 1:index + 1] = [merge(left, current)]
        else:
            left_penalty = (0 if left["kind"] == current["kind"] else 20) + abs(left["grade"] - current["grade"])
            right_penalty = (0 if right["kind"] == current["kind"] else 20) + abs(right["grade"] - current["grade"])
            if left_penalty <= right_penalty:
                result[index - 1:index + 1] = [merge(left, current)]
            else:
                result[index:index + 2] = [merge(current, right)]
        protected.clear()
    return result


def build_segments(profile: list[dict]) -> list[dict]:
    sample_km, radius = 0.1, 0.2
    maximum = profile[-1]["km"]
    samples = []
    km = 0.0
    while km < maximum:
        samples.append(km)
        km += sample_km
    samples.append(maximum)
    smoothed = []
    for km in samples:
        nearby = [point for point in profile if abs(point["km"] - km) <= radius]
        weighted = [(point["ele"], max(0.05, 1 - abs(point["km"] - km) / radius)) for point in nearby]
        smoothed.append(sum(value * weight for value, weight in weighted) / sum(weight for _, weight in weighted)
                        if weighted else interpolate(profile, km))
    micro = [refresh({"fromKm": samples[i - 1], "toKm": samples[i],
                      "startEle": smoothed[i - 1], "endEle": smoothed[i]})
             for i in range(1, len(samples)) if samples[i] > samples[i - 1]]
    grouped = []
    for item in micro:
        if grouped and grouped[-1]["kind"] == item["kind"] and abs(grouped[-1]["grade"] - item["grade"]) <= 3:
            grouped[-1] = merge(grouped[-1], item)
        else:
            grouped.append(item)
    return merge_short(grouped)


def fit_power(samples: list[tuple[float, float]]) -> tuple[float, float, float]:
    transformed = [(math.log(speed), math.log(score / (100 - score)))
                   for speed, score in samples if speed >= 3 and 0.1 < score < 99.9]
    xs, ys = zip(*transformed)
    mean_x, mean_y = statistics.mean(xs), statistics.mean(ys)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in transformed) / sum((x - mean_x) ** 2 for x in xs)
    intercept = mean_y - slope * mean_x
    predicted = [intercept + slope * x for x in xs]
    ss_total = sum((y - mean_y) ** 2 for y in ys)
    r_squared = 1 - sum((y - p) ** 2 for y, p in zip(ys, predicted)) / ss_total
    return intercept, slope, r_squared


def main() -> None:
    profile = read_profile(Path(sys.argv[1]))
    segments = build_segments(profile)
    selected = []
    for number in (30, 32, 33):
        segment = segments[number - 1]
        samples = [(point["wheelSpeed"], point["shakeScore"]) for point in profile
                   if segment["fromKm"] <= point["km"] <= segment["toKm"]
                   and point["wheelSpeed"] is not None and point["shakeScore"] is not None
                   and point["wheelSpeed"] >= 3]
        selected.extend(samples)
        print(f"{number}: {segment['fromKm']:.2f}-{segment['toKm']:.2f} km, {segment['kind']}, "
              f"grade={segment['grade']:.2f}%, n={len(samples)}, "
              f"speed={statistics.mean(x for x, _ in samples):.2f}, shake={statistics.mean(y for _, y in samples):.2f}")
    intercept, exponent, r_squared = fit_power(selected)
    print(f"log(raw) = {intercept:.6f} + {exponent:.6f}*log(speed); R2={r_squared:.4f}; n={len(selected)}")


if __name__ == "__main__":
    main()
