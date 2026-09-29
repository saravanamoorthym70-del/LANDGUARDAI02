"""
Bootstrap dataset — offline stand-in for stages 5-9 of the real
pipeline (create_real_background_locations.py ... combine_ml_dataset.py).

WHY THIS SCRIPT EXISTS
-----------------------
The full pipeline (see the other scripts in ml/scripts/) calls NASA's
catalog export and the live Open-Meteo / elevation APIs. Those calls
need outbound internet access that isn't available in every
environment (e.g. this was written in a sandboxed environment with no
route to those hosts). To still ship a *working* model — one the
FastAPI backend can actually load and serve predictions from — this
script builds a dataset using data that's already inside the repo:

  - POSITIVE class (risk=1): the 494 historical landslide records in
    frontend/src/landslideData.json. These already carry the full
    feature vector (rainfall 1/3/7d, soil moisture, elevation, slope)
    computed the same way the doc describes, so they're used as-is.

  - BACKGROUND class (risk=0): SYNTHETIC pseudo-absence samples drawn
    from distributions centered lower than the historical positives
    (less rainfall, drier soil, gentler slope), with noise so the
    classes aren't trivially separable. These are NOT real locations
    with real measured conditions.

This produces a real, working RandomForestClassifier for development
and demo purposes. Before treating results as meaningful for the
actual SIH submission, replace this bootstrap by running the real
pipeline (inspect_nasa_data.py through get_background_slope.py) on a
machine with internet access, then run combine_ml_dataset.py and
train_real_model.py normally.

Output:
  ml/dataset/LANDGUARD_FINAL_DATASET.csv  (same output path/shape the
  real pipeline produces, so train_real_model.py works unmodified)

Run:
    python -m ml.scripts.build_placeholder_dataset
"""

import json
import os

import numpy as np
import pandas as pd

from ml.scripts.common import DATASET_DIR, FEATURES, ML_DIR, TARGET_COLUMN

REPO_ROOT = os.path.dirname(ML_DIR)
LANDSLIDE_JSON = os.path.join(
    REPO_ROOT, "frontend", "src", "landslideData.json"
)
OUTPUT_CSV = os.path.join(DATASET_DIR, "LANDGUARD_FINAL_DATASET.csv")

BACKGROUND_COUNT = 649  # matches the documented 650 → 649 after one drop
RANDOM_STATE = 42

FIELD_MAP = {
    "rainfall_1d": "rainfall_1d_mm",
    "rainfall_3d": "rainfall_3d_mm",
    "rainfall_7d": "rainfall_7d_mm",
    "soil_moisture": "soil_moisture_0_7cm",
    "elevation": "elevation_m",
    "slope": "slope_deg",
}


def load_positive_class():
    with open(LANDSLIDE_JSON) as f:
        records = json.load(f)

    rows = []
    for r in records:
        row = {FIELD_MAP[k]: r[k] for k in FIELD_MAP}
        rows.append(row)

    df = pd.DataFrame(rows)
    df[TARGET_COLUMN] = 1
    return df


def generate_background(n, rng):
    # Distributions shifted lower than the historical positives (see
    # module docstring), with enough spread/noise to overlap the
    # positive class rather than being perfectly separable.
    rainfall_1d = np.clip(rng.exponential(scale=8.0, size=n), 0, None)
    rainfall_3d = rainfall_1d + np.clip(
        rng.exponential(scale=15.0, size=n), 0, None
    )
    rainfall_7d = rainfall_3d + np.clip(
        rng.exponential(scale=25.0, size=n), 0, None
    )

    soil_moisture = np.clip(rng.normal(0.28, 0.10, size=n), 0.02, 0.60)
    elevation = np.clip(rng.gamma(shape=2.0, scale=250.0, size=n), 0, 4500)
    slope = np.clip(rng.gamma(shape=1.5, scale=4.5, size=n), 0, 60)

    return pd.DataFrame(
        {
            "rainfall_1d_mm": rainfall_1d,
            "rainfall_3d_mm": rainfall_3d,
            "rainfall_7d_mm": rainfall_7d,
            "soil_moisture_0_7cm": soil_moisture,
            "elevation_m": elevation,
            "slope_deg": slope,
            TARGET_COLUMN: 0,
        }
    )


def main():
    if not os.path.exists(LANDSLIDE_JSON):
        raise SystemExit(f"Missing {LANDSLIDE_JSON}")

    positive = load_positive_class()
    print(f"Historical landslides (risk=1): {len(positive)}")

    rng = np.random.default_rng(RANDOM_STATE)
    background = generate_background(BACKGROUND_COUNT, rng)
    print(f"Synthetic background   (risk=0): {len(background)}")

    combined = pd.concat(
        [positive[FEATURES + [TARGET_COLUMN]], background[FEATURES + [TARGET_COLUMN]]],
        ignore_index=True,
    )
    combined = combined.sample(frac=1, random_state=RANDOM_STATE).reset_index(
        drop=True
    )

    combined.to_csv(OUTPUT_CSV, index=False)
    print(f"Total: {len(combined)}")
    print(f"Wrote {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
