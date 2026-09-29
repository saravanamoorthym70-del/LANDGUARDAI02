"""
Stage 2 — Rainfall + soil moisture for each historical event
(workflow doc, sections 4-5).

Input:
  ml/dataset/INDIA_TARGET_REGIONS_landslides.csv

Output:
  ml/dataset/INDIA_TARGET_REGIONS_environmental_data.csv

For every historical landslide location, pulls the Open-Meteo Historical
Weather API centered on the event date and computes:
  rainfall_1d_mm, rainfall_3d_mm, rainfall_7d_mm, soil_moisture_0_7cm

Run:
    python -m ml.scripts.get_environmental_data
"""

import os
import sys
import time

import pandas as pd
import requests

from ml.scripts.common import (
    DATASET_DIR,
    OPEN_METEO_ARCHIVE_URL,
    REQUEST_TIMEOUT_SECONDS,
)

INPUT_CSV = os.path.join(DATASET_DIR, "INDIA_TARGET_REGIONS_landslides.csv")
OUTPUT_CSV = os.path.join(
    DATASET_DIR, "INDIA_TARGET_REGIONS_environmental_data.csv"
)

REQUEST_PAUSE_SECONDS = 0.2  # be polite to the free API


def fetch_environment(latitude, longitude, event_date):
    """Fetch rainfall (1/3/7 day) and soil moisture ending on event_date."""
    end_date = pd.to_datetime(event_date).normalize()
    start_date = end_date - pd.Timedelta(days=7)

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "hourly": "precipitation,soil_moisture_0_to_7cm",
        "timezone": "UTC",
    }

    response = requests.get(
        OPEN_METEO_ARCHIVE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS
    )
    response.raise_for_status()
    data = response.json()

    hourly = data.get("hourly", {})
    precipitation = [v for v in hourly.get("precipitation", []) if v is not None]
    soil_moisture = [
        v for v in hourly.get("soil_moisture_0_to_7cm", []) if v is not None
    ]

    rainfall_1d = sum(precipitation[-24:]) if precipitation else None
    rainfall_3d = sum(precipitation[-72:]) if precipitation else None
    rainfall_7d = sum(precipitation[-168:]) if precipitation else None
    current_soil_moisture = soil_moisture[-1] if soil_moisture else None

    return {
        "rainfall_1d_mm": rainfall_1d,
        "rainfall_3d_mm": rainfall_3d,
        "rainfall_7d_mm": rainfall_7d,
        "soil_moisture_0_7cm": current_soil_moisture,
    }


def main():
    if not os.path.exists(INPUT_CSV):
        sys.exit(f"Missing {INPUT_CSV} — run inspect_nasa_data.py first.")

    df = pd.read_csv(INPUT_CSV)
    records = []

    for i, row in df.iterrows():
        try:
            env = fetch_environment(
                row["latitude"], row["longitude"], row["event_date"]
            )
        except Exception as exc:  # noqa: BLE001 — log and continue
            print(f"[{i}] failed: {exc}")
            env = {
                "rainfall_1d_mm": None,
                "rainfall_3d_mm": None,
                "rainfall_7d_mm": None,
                "soil_moisture_0_7cm": None,
            }

        record = row.to_dict()
        record.update(env)
        records.append(record)

        if i % 25 == 0:
            print(f"{i + 1}/{len(df)} events processed")

        time.sleep(REQUEST_PAUSE_SECONDS)

    out = pd.DataFrame(records)
    out.to_csv(OUTPUT_CSV, index=False)
    print(f"\nWrote {OUTPUT_CSV} ({len(out)} rows)")


if __name__ == "__main__":
    main()
