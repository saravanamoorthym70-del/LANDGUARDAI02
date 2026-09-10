"""
Stage 7 — Elevation for background locations (mirrors
get_elevation_data.py, workflow doc section 6).

Input:
  ml/dataset/BACKGROUND_ENVIRONMENTAL_DATA.csv

Output:
  ml/dataset/BACKGROUND_TERRAIN_DATA.csv

Run:
    python -m ml.scripts.get_background_elevation
"""

import os
import sys

import pandas as pd

from ml.scripts.common import DATASET_DIR
from ml.scripts.get_elevation_data import fetch_elevations, BATCH_SIZE

INPUT_CSV = os.path.join(DATASET_DIR, "BACKGROUND_ENVIRONMENTAL_DATA.csv")
OUTPUT_CSV = os.path.join(DATASET_DIR, "BACKGROUND_TERRAIN_DATA.csv")


def main():
    if not os.path.exists(INPUT_CSV):
        sys.exit(
            f"Missing {INPUT_CSV} — run get_background_environmental_data.py first."
        )

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
    print(f"\nWrote {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
