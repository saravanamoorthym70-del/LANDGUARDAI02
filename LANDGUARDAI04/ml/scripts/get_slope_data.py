"""
Stage 4 — Slope (workflow doc, section 7).

Input:
  ml/dataset/INDIA_TARGET_REGIONS_terrain_data.csv

Output:
  ml/dataset/INDIA_TARGET_REGIONS_slope_data.csv

For each location, requests a 3x3 grid of surrounding elevations and
estimates slope from the elevation gradient — the exact same approach
used live in backend/main.py's /live-risk endpoint, so historical
training data and live inference are computed consistently.

Run:
    python -m ml.scripts.get_slope_data
"""

import os
import sys
import time

import numpy as np
import pandas as pd
import requests

from ml.scripts.common import (
    DATASET_DIR,
    OPEN_METEO_ELEVATION_URL,
    REQUEST_TIMEOUT_SECONDS,
)

INPUT_CSV = os.path.join(DATASET_DIR, "INDIA_TARGET_REGIONS_terrain_data.csv")
OUTPUT_CSV = os.path.join(DATASET_DIR, "INDIA_TARGET_REGIONS_slope_data.csv")

GRID_OFFSET_DEG = 0.001
CELL_SIZE_M = 100.0


def slope_for_point(latitude, longitude):
    lat_offsets = [-GRID_OFFSET_DEG, 0, GRID_OFFSET_DEG]
    lon_offsets = [-GRID_OFFSET_DEG, 0, GRID_OFFSET_DEG]

    latitudes = [latitude + dlat for dlat in lat_offsets for _ in lon_offsets]
    longitudes = [longitude + dlon for _ in lat_offsets for dlon in lon_offsets]

    params = {
        "latitude": ",".join(map(str, latitudes)),
        "longitude": ",".join(map(str, longitudes)),
    }
    for attempt in range(4):
        try:
            response = requests.get(
                OPEN_METEO_ELEVATION_URL,
                params=params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            grid = np.array(response.json()["elevation"]).reshape(3, 3)
            break
        except (requests.RequestException, KeyError, TypeError, ValueError):
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))
    gradient_y, gradient_x = np.gradient(grid, CELL_SIZE_M)
    slope_deg = np.degrees(
        np.arctan(np.sqrt(gradient_x**2 + gradient_y**2))
    )

    return float(slope_deg[1, 1])


def main():
    if not os.path.exists(INPUT_CSV):
        sys.exit(f"Missing {INPUT_CSV} — run get_elevation_data.py first.")

    df = pd.read_csv(INPUT_CSV)
    slopes = []

    for i, row in df.iterrows():
        try:
            slopes.append(slope_for_point(row["latitude"], row["longitude"]))
        except Exception as exc:  # noqa: BLE001
            print(f"[{i}] slope failed: {exc}")
            slopes.append(None)

        if i % 25 == 0:
            print(f"{i + 1}/{len(df)} slopes computed")

    df["slope_deg"] = slopes
    df.to_csv(OUTPUT_CSV, index=False)

    valid = df["slope_deg"].dropna()
    print(f"\nMean slope ≈ {valid.mean():.2f}°")
    print(f"Maximum ≈ {valid.max():.2f}°")
    print(f"Wrote {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
