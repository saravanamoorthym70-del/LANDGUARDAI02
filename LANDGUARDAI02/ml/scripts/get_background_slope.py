"""
Stage 8 — Slope for background locations (mirrors get_slope_data.py,
workflow doc section 7).

Input:
  ml/dataset/BACKGROUND_TERRAIN_DATA.csv

Output:
  ml/dataset/BACKGROUND_SLOPE_DATA.csv

Run:
    python -m ml.scripts.get_background_slope
"""

import os
import sys

import pandas as pd

from ml.scripts.common import DATASET_DIR
from ml.scripts.get_slope_data import slope_for_point

INPUT_CSV = os.path.join(DATASET_DIR, "BACKGROUND_TERRAIN_DATA.csv")
OUTPUT_CSV = os.path.join(DATASET_DIR, "BACKGROUND_SLOPE_DATA.csv")


def main():
    if not os.path.exists(INPUT_CSV):
        sys.exit(f"Missing {INPUT_CSV} — run get_background_elevation.py first.")

    df = pd.read_csv(INPUT_CSV)
    slopes = []

    for i, row in df.iterrows():
        try:
            slopes.append(slope_for_point(row["latitude"], row["longitude"]))
        except Exception as exc:  # noqa: BLE001
            print(f"[{i}] slope failed: {exc}")
            slopes.append(None)

        if i % 25 == 0:
            print(f"{i + 1}/{len(df)} background slopes computed")

    df["slope_deg"] = slopes

    # Section 9: one missing slope value gets dropped downstream in
    # combine_ml_dataset.py, matching the documented 650 → 649 count.
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nWrote {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
