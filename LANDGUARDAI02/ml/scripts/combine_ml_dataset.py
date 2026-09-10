"""
Stage 9 — Combine into the final ML dataset (workflow doc, section 11).

Inputs:
  ml/dataset/INDIA_TARGET_REGIONS_slope_data.csv   (historical, risk=1)
  ml/dataset/BACKGROUND_SLOPE_DATA.csv             (background, risk=0)

Output:
  ml/dataset/LANDGUARD_FINAL_DATASET.csv

Run:
    python -m ml.scripts.combine_ml_dataset
"""

import os
import sys

import pandas as pd

from ml.scripts.common import DATASET_DIR, FEATURES, TARGET_COLUMN

HISTORICAL_CSV = os.path.join(DATASET_DIR, "INDIA_TARGET_REGIONS_slope_data.csv")
BACKGROUND_CSV = os.path.join(DATASET_DIR, "BACKGROUND_SLOPE_DATA.csv")
OUTPUT_CSV = os.path.join(DATASET_DIR, "LANDGUARD_FINAL_DATASET.csv")


def main():
    for path in (HISTORICAL_CSV, BACKGROUND_CSV):
        if not os.path.exists(path):
            sys.exit(f"Missing {path} — run the earlier pipeline stages first.")

    historical = pd.read_csv(HISTORICAL_CSV)
    historical[TARGET_COLUMN] = 1

    background = pd.read_csv(BACKGROUND_CSV)
    background[TARGET_COLUMN] = 0

    columns = FEATURES + [TARGET_COLUMN]

    historical = historical[columns].dropna()
    background = background[columns].dropna()

    print(f"Historical landslides (risk=1): {len(historical)}")
    print(f"Background locations   (risk=0): {len(background)}")

    combined = pd.concat([historical, background], ignore_index=True)
    before = len(combined)
    combined = combined.drop_duplicates().reset_index(drop=True)
    print(f"Exact duplicate rows removed: {before - len(combined)}")
    combined = combined.sample(frac=1, random_state=42).reset_index(drop=True)

    combined.to_csv(OUTPUT_CSV, index=False)

    print(f"Total: {len(combined)}")
    print(f"Wrote {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
