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

from ml.scripts.common import DATASET_DIR, MODEL_FEATURES, TARGET_COLUMN, region_for_state

HISTORICAL_CSV = os.path.join(DATASET_DIR, "INDIA_TARGET_REGIONS_terrain_data.csv")
BACKGROUND_CSV = os.path.join(DATASET_DIR, "BACKGROUND_TERRAIN_DATA.csv")
OUTPUT_CSV = os.path.join(DATASET_DIR, "LANDGUARD_FINAL_DATASET.csv")
OPTIONAL_CONTEXT_COLUMNS = ("slope_deg",)
METADATA_COLUMNS = (
  "latitude",
  "longitude",
  "state",
  "region",
  "event_id",
  "event_date",
  "sample_date",
  "sample_type",
)


def main():
    for path in (HISTORICAL_CSV, BACKGROUND_CSV):
        if not os.path.exists(path):
            sys.exit(f"Missing {path} — run the earlier pipeline stages first.")

    historical = pd.read_csv(HISTORICAL_CSV)
    historical[TARGET_COLUMN] = 1
    historical["sample_type"] = "historical_event"

    background = pd.read_csv(BACKGROUND_CSV)
    background[TARGET_COLUMN] = 0
    background["sample_type"] = "background"

    for frame in (historical, background):
      if "region" not in frame and "state" in frame:
        frame["region"] = frame["state"].map(region_for_state)
      for column in (*METADATA_COLUMNS, *OPTIONAL_CONTEXT_COLUMNS):
        if column not in frame:
          frame[column] = pd.NA

    columns = [
      *MODEL_FEATURES,
      TARGET_COLUMN,
      *METADATA_COLUMNS,
      *OPTIONAL_CONTEXT_COLUMNS,
    ]

    required_columns = list(MODEL_FEATURES) + [TARGET_COLUMN]
    historical = historical[columns].dropna(subset=required_columns)
    background = background[columns].dropna(subset=required_columns)

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
