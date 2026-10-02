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
import re
import sys

import pandas as pd

from ml.scripts.common import DATASET_DIR, TARGET_STATES, region_for_state

RAW_CSV = os.path.join(DATASET_DIR, "NASA_Global_Landslide_Catalog.csv")
INDIA_CSV = os.path.join(DATASET_DIR, "INDIA_landslides.csv")
OUTPUT_CSV = os.path.join(DATASET_DIR, "INDIA_TARGET_REGIONS_landslides.csv")
MAX_LOCATION_ACCURACY_KM = 1.0

# The NASA GLC export uses these column names; we normalize to the
# lowercase snake_case names used throughout the rest of the pipeline.
COLUMN_MAP = {
    "event_id": "event_id",
    "event_date": "event_date",
    "event_title": "event_title",
    "location_description": "location",
    "latitude": "latitude",
    "longitude": "longitude",
    "location_accuracy": "location_accuracy",
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


def parse_location_accuracy_km(value):
    if pd.isna(value):
        return None
    normalized = str(value).strip().lower()
    if normalized == "exact":
        return 0.0
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*km", normalized)
    return float(match.group(1)) if match else None


def filter_accurate_events(events, max_accuracy_km=MAX_LOCATION_ACCURACY_KM):
    if "location_accuracy" not in events.columns:
        return events.copy(), {
            "available": False,
            "input_rows": int(len(events)),
            "retained_rows": int(len(events)),
            "excluded_rows": 0,
            "max_accuracy_km": float(max_accuracy_km),
        }

    accuracy_km = events["location_accuracy"].map(parse_location_accuracy_km)
    retained = accuracy_km.notna() & accuracy_km.le(max_accuracy_km)
    filtered = events.loc[retained].copy()
    filtered["location_accuracy_km"] = accuracy_km.loc[retained].astype(float)
    return filtered, {
        "available": True,
        "input_rows": int(len(events)),
        "retained_rows": int(retained.sum()),
        "excluded_rows": int((~retained).sum()),
        "max_accuracy_km": float(max_accuracy_km),
    }


def main():
    df = load_raw()
    print(f"NASA Global Landslide Catalog → {len(df)} records")

    df = df.dropna(subset=["latitude", "longitude"])

    india = df[df["country"].astype(str).str.strip() == "India"].copy()
    india.to_csv(INDIA_CSV, index=False)
    print(f"India → {len(india)} records")

    india["state"] = india["state"].astype(str).str.strip()
    target = india[india["state"].isin(TARGET_STATES)].copy()
    target, accuracy_summary = filter_accurate_events(target)
    if accuracy_summary["available"]:
        print(
            "Location accuracy <= "
            f"{MAX_LOCATION_ACCURACY_KM:g} km: "
            f"{accuracy_summary['retained_rows']}/{accuracy_summary['input_rows']} "
            "events retained; unmeasured/less-accurate records excluded."
        )
    else:
        print(
            "Location accuracy unavailable; no events were filtered. "
            "Available event columns: " + ", ".join(target.columns)
        )
    target["region"] = target["state"].apply(region_for_state)

    target.to_csv(OUTPUT_CSV, index=False)

    print(f"Target regions → {len(target)} records")
    print(target["region"].value_counts().to_string())
    print(f"\nWrote {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
