"""
Stage 3 — Elevation (workflow doc, section 6).

Input:
  ml/dataset/INDIA_TARGET_REGIONS_environmental_data.csv

Output:
  ml/dataset/INDIA_TARGET_REGIONS_terrain_data.csv

Batches all locations into the Open-Meteo Elevation API (which accepts
comma-separated lat/lon lists) rather than one request per row.

Run:
    python -m ml.scripts.get_elevation_data
"""

import os
import sys
import time

import pandas as pd
import requests

from ml.scripts.common import (
    DATASET_DIR,
    OPEN_METEO_ELEVATION_URL,
    REQUEST_TIMEOUT_SECONDS,
)

INPUT_CSV = os.path.join(
    DATASET_DIR, "INDIA_TARGET_REGIONS_environmental_data.csv"
)
OUTPUT_CSV = os.path.join(DATASET_DIR, "INDIA_TARGET_REGIONS_terrain_data.csv")

BATCH_SIZE = 50  # Smaller batches reduce rate-limit pressure on the public API


def fetch_elevations(latitudes, longitudes):
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
            return response.json()["elevation"]
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))


def main():
    if not os.path.exists(INPUT_CSV):
        sys.exit(f"Missing {INPUT_CSV} — run get_environmental_data.py first.")

    df = pd.read_csv(INPUT_CSV)
    elevations = []

    for start in range(0, len(df), BATCH_SIZE):
        chunk = df.iloc[start : start + BATCH_SIZE]
        try:
            values = fetch_elevations(
                chunk["latitude"].tolist(), chunk["longitude"].tolist()
            )
        except Exception as exc:  # noqa: BLE001
            print(f"batch {start} failed: {exc}")
            values = [None] * len(chunk)

        elevations.extend(values)
        print(f"{min(start + BATCH_SIZE, len(df))}/{len(df)} elevations fetched")

    df["elevation_m"] = elevations
    df.to_csv(OUTPUT_CSV, index=False)

    available = df["elevation_m"].notna().sum()
    print(f"\n{available}/{len(df)} elevation values available")
    print(f"Wrote {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
