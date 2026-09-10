"""
Stage 1 — Historical landslide data (workflow doc, section 2-3).

Input:
  ml/dataset/NASA_Global_Landslide_Catalog.csv
  Download from: https://data.nasa.gov/dataset/global-landslide-catalog-export

Output:
  ml/dataset/INDIA_TARGET_REGIONS_landslides.csv

This filters the raw NASA Global Landslide Catalog (worldwide) down to
India, then down to the 13 target states (8 NER + 5 South India
extension) used by LANDGUARD AI.

Run:
    python -m ml.scripts.inspect_nasa_data
"""

import os
import sys

import pandas as pd

from ml.scripts.common import DATASET_DIR, TARGET_STATES, region_for_state

RAW_CSV = os.path.join(DATASET_DIR, "NASA_Global_Landslide_Catalog.csv")
INDIA_CSV = os.path.join(DATASET_DIR, "INDIA_landslides.csv")
OUTPUT_CSV = os.path.join(DATASET_DIR, "INDIA_TARGET_REGIONS_landslides.csv")

# The NASA GLC export uses these column names; we normalize to the
# lowercase snake_case names used throughout the rest of the pipeline.
COLUMN_MAP = {
    "event_id": "event_id",
    "event_date": "event_date",
    "event_title": "event_title",
    "location_description": "location",
    "latitude": "latitude",
    "longitude": "longitude",
    "landslide_category": "landslide_category",
    "landslide_trigger": "landslide_trigger",
    "landslide_size": "landslide_size",
    "fatality_count": "fatalities",
    "injury_count": "injuries",
    "admin_division_name": "state",
    "country_name": "country",
}


def load_raw():
    if not os.path.exists(RAW_CSV):
        sys.exit(
            "Missing "
            + RAW_CSV
            + "\nDownload the NASA Global Landslide Catalog export and "
            "place it there before running this script."
        )

    df = pd.read_csv(RAW_CSV, low_memory=False)

    available = {k: v for k, v in COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=available)

    keep = [v for v in COLUMN_MAP.values() if v in df.columns]
    return df[keep]


def main():
    df = load_raw()
    print(f"NASA Global Landslide Catalog → {len(df)} records")

    df = df.dropna(subset=["latitude", "longitude"])

    india = df[df["country"].astype(str).str.strip() == "India"].copy()
    india.to_csv(INDIA_CSV, index=False)
    print(f"India → {len(india)} records")

    india["state"] = india["state"].astype(str).str.strip()
    target = india[india["state"].isin(TARGET_STATES)].copy()
    target["region"] = target["state"].apply(region_for_state)

    target.to_csv(OUTPUT_CSV, index=False)

    print(f"Target regions → {len(target)} records")
    print(target["region"].value_counts().to_string())
    print(f"\nWrote {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
