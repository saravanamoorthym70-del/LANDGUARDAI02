"""
Shared constants and helpers used by every script in the LANDGUARD AI
data pipeline (ml/scripts/*.py).

Keeping these in one place means every stage of the pipeline agrees on:
  - which states count as "target regions" (NER + the South India extension)
  - the feature schema fed into the model
  - basic geo helpers (haversine distance) used for background sampling
"""

import math
import os

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ML_DIR = os.path.dirname(SCRIPTS_DIR)
DATASET_DIR = os.path.join(ML_DIR, "dataset")
MODELS_DIR = os.path.join(ML_DIR, "models")

os.makedirs(DATASET_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)

# ------------------------------------------------------------------
# Target regions (see workflow doc, section 3)
# ------------------------------------------------------------------

NER_STATES = [
    "Assam",
    "Arunachal Pradesh",
    "Meghalaya",
    "Manipur",
    "Mizoram",
    "Nagaland",
    "Sikkim",
    "Tripura",
]

SOUTH_STATES = [
    "Tamil Nadu",
    "Kerala",
    "Karnataka",
    "Andhra Pradesh",
    "Telangana",
]

TARGET_STATES = NER_STATES + SOUTH_STATES


def region_for_state(state: str) -> str:
    """Return 'NER', 'SOUTH', or 'OTHER' for a given state name."""
    if state in NER_STATES:
        return "NER"
    if state in SOUTH_STATES:
        return "SOUTH"
    return "OTHER"


# ------------------------------------------------------------------
# ML feature schema — MUST match backend/ml_predictor.py FEATURES
# ------------------------------------------------------------------

FEATURES = [
    "rainfall_1d_mm",
    "rainfall_3d_mm",
    "rainfall_7d_mm",
    "soil_moisture_0_7cm",
    "elevation_m",
    "slope_deg",
]

TARGET_COLUMN = "risk"

# ------------------------------------------------------------------
# Open-Meteo endpoints
# ------------------------------------------------------------------

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"

REQUEST_TIMEOUT_SECONDS = 30


# ------------------------------------------------------------------
# Geo helpers
# ------------------------------------------------------------------

def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two lat/lon points, in kilometres."""
    r = 6371.0088

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return r * c


def min_distance_km(lat, lon, points):
    """Minimum haversine distance (km) from (lat, lon) to any point in
    `points`, an iterable of (lat, lon) tuples. Returns inf for an empty
    iterable."""
    best = math.inf
    for plat, plon in points:
        d = haversine_km(lat, lon, plat, plon)
        if d < best:
            best = d
    return best

RANDOM_STATE = 42
