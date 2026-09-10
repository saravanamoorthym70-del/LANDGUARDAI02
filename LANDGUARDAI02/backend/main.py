import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import requests
import numpy as np

from backend.ml_predictor import predict_risk, model_is_loaded


# ============================================================
# LANDGUARD AI - FASTAPI BACKEND
# ============================================================

app = FastAPI(
    title="LANDGUARD AI",
    description="AI-Based Landslide Risk Monitoring System",
    version="2.0"
)


# ============================================================
# CORS
#
# Defaults cover local Vite dev. In production, set the
# CORS_ALLOWED_ORIGINS env var to a comma-separated list of the real
# frontend origin(s), e.g. "https://landguard.example.org".
# ============================================================

_default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]

_env_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "")
_extra_origins = [o.strip() for o in _env_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_default_origins + _extra_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# REQUEST MODEL
# ============================================================

class RiskRequest(BaseModel):
    rainfall_1d_mm: float = Field(ge=0, le=2000)
    rainfall_3d_mm: float = Field(ge=0, le=3000)
    rainfall_7d_mm: float = Field(ge=0, le=4000)
    soil_moisture_0_7cm: float = Field(ge=0, le=1)
    elevation_m: float = Field(ge=-500, le=9000)
    slope_deg: float = Field(ge=0, le=90)


# ============================================================
# HOME
# ============================================================

@app.get("/")
def home():
    return {
        "message": "LANDGUARD AI Backend Connected Successfully!",
        "status": "success",
        "model": "Random Forest"
    }


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "model": "loaded" if model_is_loaded() else "unavailable (rule-based fallback active)"
    }


# ============================================================
# AI RISK PREDICTION
# ============================================================

@app.post("/predict-risk")
def predict(data: RiskRequest):

    result = predict_risk(
        rainfall_1d_mm=data.rainfall_1d_mm,
        rainfall_3d_mm=data.rainfall_3d_mm,
        rainfall_7d_mm=data.rainfall_7d_mm,
        soil_moisture_0_7cm=data.soil_moisture_0_7cm,
        elevation_m=data.elevation_m,
        slope_deg=data.slope_deg
    )

    return result


# ============================================================
# LIVE ENVIRONMENT
# ============================================================

@app.get("/live-environment")
def live_environment(latitude: float, longitude: float):

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise HTTPException(status_code=422, detail="Invalid latitude/longitude.")

    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "precipitation,soil_moisture_0_to_7cm",
        "past_days": 7,
        "forecast_days": 0,
        "timezone": "UTC",
    }

    try:
        response = requests.get(url, params=params, timeout=30)
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to retrieve live environmental data: {exc}"
        ) from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Failed to retrieve live environmental data."
        )

    data = response.json()

    hourly = data.get("hourly", {})

    times = hourly.get("time", [])
    precipitation = hourly.get("precipitation", [])
    soil_moisture = hourly.get(
        "soil_moisture_0_to_7cm", []
    )

    if not precipitation:
        raise HTTPException(
            status_code=500,
            detail="Rainfall data unavailable."
        )

    # =====================================================
    # LAST 168 HOURS = 7 DAYS
    # =====================================================

    if len(precipitation) < 24:
        raise HTTPException(status_code=502, detail="Insufficient hourly rainfall data returned by weather service.")

    rainfall_7_days = precipitation[-168:]

    # =====================================================
    # RAINFALL WINDOWS
    # =====================================================

    rainfall_1d = sum(
        value for value in precipitation[-24:]
        if value is not None
    )

    rainfall_3d = sum(
        value for value in precipitation[-72:]
        if value is not None
    )

    rainfall_7d = sum(
        value for value in precipitation[-168:]
        if value is not None
    )

    # =====================================================
    # CURRENT SOIL MOISTURE
    # =====================================================

    valid_soil = [
        value
        for value in soil_moisture[-168:]
        if value is not None
    ]

    current_soil_moisture = (
        valid_soil[-1]
        if valid_soil
        else None
    )

    # =====================================================
    # ELEVATION
    # =====================================================

    elevation = data.get("elevation")

    # =====================================================
    # CREATE DAILY RAINFALL DATA
    # =====================================================

    daily_rainfall = {}

    for time_value, rainfall_value in zip(
        times,
        precipitation
    ):

        if rainfall_value is None:
            continue

        date_value = time_value[:10]

        if date_value not in daily_rainfall:
            daily_rainfall[date_value] = 0

        daily_rainfall[date_value] += rainfall_value

    rainfall_daily = [
        {
            "date": date_value,
            "rainfall_mm": round(
                rainfall_value,
                2
            ),
        }
        for date_value, rainfall_value
        in sorted(daily_rainfall.items())
    ]

    return {
        "latitude": latitude,
        "longitude": longitude,

        "rainfall_1d_mm": round(
            rainfall_1d,
            2
        ),

        "rainfall_3d_mm": round(
            rainfall_3d,
            2
        ),

        "rainfall_7d_mm": round(
            rainfall_7d,
            2
        ),

        "soil_moisture_0_7cm": (
            round(
                current_soil_moisture,
                3
            )
            if current_soil_moisture is not None
            else None
        ),

        "elevation_m": elevation,

        "rainfall_daily": rainfall_daily,
    }

# ============================================================
# LIVE RISK
# ============================================================

@app.get("/live-risk")
def live_risk(
    latitude: float,
    longitude: float
):

    # ========================================================
    # STEP 1 - GET LIVE ENVIRONMENT
    # ========================================================

    environment = live_environment(
        latitude=latitude,
        longitude=longitude
    )


    # ========================================================
    # STEP 2 - CREATE 3x3 ELEVATION GRID
    # ========================================================

    offset = 0.001

    latitudes = [
        latitude - offset,
        latitude - offset,
        latitude - offset,

        latitude,
        latitude,
        latitude,

        latitude + offset,
        latitude + offset,
        latitude + offset
    ]

    longitudes = [
        longitude - offset,
        longitude,
        longitude + offset,

        longitude - offset,
        longitude,
        longitude + offset,

        longitude - offset,
        longitude,
        longitude + offset
    ]


    # ========================================================
    # STEP 3 - GET ELEVATION
    # ========================================================

    elevation_url = (
        "https://api.open-meteo.com/v1/elevation"
    )

    try:
        elevation_response = requests.get(
            elevation_url,
            params={
                "latitude": ",".join(
                    map(str, latitudes)
                ),
                "longitude": ",".join(
                    map(str, longitudes)
                )
            },
            timeout=30
        )
        elevation_response.raise_for_status()
        elevation_data = elevation_response.json()
        elevations = elevation_data.get("elevation")
        if not isinstance(elevations, list) or len(elevations) != 9 or any(v is None for v in elevations):
            raise ValueError("invalid elevation grid")
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to retrieve elevation data: {exc}"
        ) from exc


    # ========================================================
    # STEP 4 - CONVERT TO 3x3 GRID
    # ========================================================

    try:
        elevation_grid = np.array(
            elevations
        ).reshape(3, 3)
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="Elevation service returned an unexpected response."
        ) from exc


    # ========================================================
    # STEP 5 - CALCULATE SLOPE
    # ========================================================

    # Approximate grid spacing in metres
    cell_size = 100.0

    gradient_y, gradient_x = np.gradient(
        elevation_grid,
        cell_size
    )

    # Calculate slope
    slope_radians = np.arctan(
        np.sqrt(
            gradient_x ** 2 +
            gradient_y ** 2
        )
    )

    slope_degrees = np.degrees(
        slope_radians
    )

    # Centre cell = requested location
    slope_deg = float(
        slope_degrees[1, 1]
    )


    # ========================================================
    # STEP 6 - RUN AI MODEL
    # ========================================================

    # The /live-environment forecast response doesn't always include
    # an elevation field; fall back to the centre of the elevation
    # grid we already fetched for the slope calculation above, so a
    # missing value here doesn't crash prediction with a None/NaN
    # feature.
    elevation_m = environment["elevation_m"]
    if elevation_m is None:
        elevation_m = float(elevation_grid[1, 1])

    soil_moisture = environment["soil_moisture_0_7cm"]
    if soil_moisture is None:
        raise HTTPException(
            status_code=502,
            detail="Soil moisture data unavailable for this location right now."
        )

    # Keep the returned environment payload consistent with whatever
    # elevation value prediction actually used.
    environment["elevation_m"] = elevation_m

    result = predict_risk(

        rainfall_1d_mm=environment[
            "rainfall_1d_mm"
        ],

        rainfall_3d_mm=environment[
            "rainfall_3d_mm"
        ],

        rainfall_7d_mm=environment[
            "rainfall_7d_mm"
        ],

        soil_moisture_0_7cm=soil_moisture,

        elevation_m=elevation_m,

        slope_deg=slope_deg
    )


    # ========================================================
    # STEP 7 - FINAL RESPONSE
    # ========================================================

    return {

        "location": {
            "latitude": latitude,
            "longitude": longitude
        },

        "environment": environment,

        "terrain": {
            "slope_deg": round(
                slope_deg,
                2
            )
        },

        "prediction": result
    }


# ============================================================
# REVERSE GEOCODING
# ============================================================

@app.get("/reverse-geocode")
def reverse_geocode(
    latitude: float,
    longitude: float
):

    url = (
        "https://nominatim.openstreetmap.org/reverse"
    )

    params = {
        "lat": latitude,
        "lon": longitude,
        "format": "json",
        "zoom": 10,
        "addressdetails": 1
    }

    headers = {
        "User-Agent": "LANDGUARD-AI/1.0"
    }

    try:
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=20
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Reverse geocoding failed: {exc}"
        ) from exc

    address = data.get(
        "address",
        {}
    )

    return {

        "display_name": data.get(
            "display_name",
            "Unknown location"
        ),

        "village": address.get(
            "village"
        ),

        "town": address.get(
            "town"
        ),

        "city": address.get(
            "city"
        ),

        "state": address.get(
            "state"
        ),

        "country": address.get(
            "country"
        )
    }