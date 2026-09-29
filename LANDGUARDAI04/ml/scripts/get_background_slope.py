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
import time

import pandas as pd

from ml.scripts.common import DATASET_DIR
from ml.scripts.get_slope_data import slope_for_point

INPUT_CSV = os.path.join(DATASET_DIR, "BACKGROUND_TERRAIN_DATA.csv")
OUTPUT_CSV = os.path.join(DATASET_DIR, "BACKGROUND_SLOPE_DATA.csv")
REQUEST_PAUSE_SECONDS = 1.25
CHECKPOINT_EVERY = 20
MAX_RATE_LIMIT_RETRIES = 5


def _location_key(latitude, longitude):
    return round(float(latitude), 8), round(float(longitude), 8)


def _load_completed_slopes():
    if not os.path.exists(OUTPUT_CSV):
        return {}

    previous = pd.read_csv(OUTPUT_CSV)
    if not {"latitude", "longitude", "slope_deg"}.issubset(previous.columns):
        return {}

    return {
        _location_key(row.latitude, row.longitude): float(row.slope_deg)
        for row in previous.itertuples()
        if pd.notna(row.slope_deg)
    }


def _save_checkpoint(data, slopes):
    checkpoint = data.copy()
    checkpoint["slope_deg"] = slopes
    temporary_path = f"{OUTPUT_CSV}.tmp"
    checkpoint.to_csv(temporary_path, index=False)
    os.replace(temporary_path, OUTPUT_CSV)


def main():
    if not os.path.exists(INPUT_CSV):
        sys.exit(f"Missing {INPUT_CSV} — run get_background_elevation.py first.")

    df = pd.read_csv(INPUT_CSV)
    completed = _load_completed_slopes()
    slopes = [
        completed.get(_location_key(row.latitude, row.longitude))
        for row in df.itertuples()
    ]
    pending_indices = [index for index, slope in enumerate(slopes) if slope is None]
    print(f"Reusing {len(df) - len(pending_indices)} cached slopes")

    for completed_count, index in enumerate(pending_indices, start=1):
        row = df.iloc[index]
        retry_count = 0
        while True:
            try:
                slopes[index] = slope_for_point(row["latitude"], row["longitude"])
                break
            except Exception as exc:  # noqa: BLE001
                response = getattr(exc, "response", None)
                if getattr(response, "status_code", None) == 429:
                    if retry_count >= MAX_RATE_LIMIT_RETRIES:
                        _save_checkpoint(df, slopes)
                        raise RuntimeError(
                            "Elevation service rate limit persisted; completed slopes were checkpointed."
                        ) from exc
                    retry_after = getattr(response, "headers", {}).get("Retry-After")
                    try:
                        delay = float(retry_after)
                    except (TypeError, ValueError):
                        delay = 60.0 * (2 ** retry_count)
                    retry_count += 1
                    print(f"Rate limited; retrying in {delay:g}s")
                    time.sleep(delay)
                    continue

                print(f"[{index}] slope failed: {exc}")
                break

        if completed_count % CHECKPOINT_EVERY == 0:
            _save_checkpoint(df, slopes)
            print(f"{index + 1}/{len(df)} rows processed; checkpoint saved")
        time.sleep(REQUEST_PAUSE_SECONDS)

    _save_checkpoint(df, slopes)
    print(f"\nWrote {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
