from __future__ import annotations

import csv
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def valid_float(value: str) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def segment_means(path: Path) -> list[dict]:
    groups: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            if row.get("surface_known_flag") != "1" or row.get("training_use_flag") != "1":
                continue
            if row.get("transition_flag") == "1" or row.get("stop_flag") == "1" or row.get("ride_mode") != "jazda":
                continue
            speed = valid_float(row.get("wheel_speed_mean_kmh", ""))
            shake = valid_float(row.get("shake_score", ""))
            if speed is None or shake is None or speed < 3 or not (0.1 < shake < 99.9):
                continue
            groups[(row["surface_label"], row["segment_id"])].append((speed, shake))

    result = []
    for (surface, segment), values in groups.items():
        if len(values) < 15:
            continue
        # Geometric means make segment-level percentage comparisons auditable.
        result.append({
            "surface": surface,
            "segment": segment,
            "n": len(values),
            "speed": math.exp(statistics.mean(math.log(speed) for speed, _ in values)),
            "shake": math.exp(statistics.mean(math.log(shake) for _, shake in values)),
        })
    return result


def slope(rows: list[dict]) -> tuple[float, float]:
    xs = [math.log(row["speed"]) for row in rows]
    ys = [math.log(row["shake"]) for row in rows]
    mean_x, mean_y = statistics.mean(xs), statistics.mean(ys)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    beta = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
    predicted = [mean_y + beta * (x - mean_x) for x in xs]
    total = sum((y - mean_y) ** 2 for y in ys)
    r2 = 1 - sum((y - prediction) ** 2 for y, prediction in zip(ys, predicted)) / total if total else 0
    return beta, r2


def fixed_effect_slope(rows: list[dict]) -> tuple[float, float]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[row["surface"]].append(row)
    x_deviations, y_deviations = [], []
    for items in groups.values():
        if len(items) < 3:
            continue
        xs = [math.log(row["speed"]) for row in items]
        ys = [math.log(row["shake"]) for row in items]
        mean_x, mean_y = statistics.mean(xs), statistics.mean(ys)
        x_deviations.extend(x - mean_x for x in xs)
        y_deviations.extend(y - mean_y for y in ys)
    beta = sum(x * y for x, y in zip(x_deviations, y_deviations)) / sum(x * x for x in x_deviations)
    total = sum(y * y for y in y_deviations)
    r2 = 1 - sum((y - beta * x) ** 2 for x, y in zip(x_deviations, y_deviations)) / total
    return beta, r2


def main() -> None:
    rows = segment_means(Path(sys.argv[1]))
    surfaces: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        surfaces[row["surface"]].append(row)
    for surface, items in sorted(surfaces.items()):
        if len(items) < 3:
            continue
        beta, r2 = slope(items)
        print(f"{surface}: segments={len(items)}, speed={min(x['speed'] for x in items):.2f}-"
              f"{max(x['speed'] for x in items):.2f}, elasticity={beta:.4f}, R2={r2:.3f}")
    beta, r2 = fixed_effect_slope(rows)
    print(f"GLOBAL_FIXED_EFFECT: segments={len(rows)}, elasticity={beta:.6f}, within_R2={r2:.4f}")


if __name__ == "__main__":
    main()
