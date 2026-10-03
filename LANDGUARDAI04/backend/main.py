import csv
import math
import os
from datetime import date, datetime, timedelta

from typing import Any

from fastapi import FastAPI, HTTPException, Query, params
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import requests
import numpy as np

from backend.ml_predictor import predict_risk, model_is_loaded
from backend.record_store import (
    create_record,
    delete_all_records,
    get_record,
    init_db,
    list_records,
)
from backend.risk_grid import get_risk_grid_geojson, parse_bbox
from backend.exposure import get_exposure_geojson
from backend.replay import replay_location


# ============================================================
# LANDGUARD AI - FASTAPI BACKEND
# ============================================================

app = FastAPI(
    title="LANDGUARD AI",
    description="AI-Based Landslide Risk Monitoring System",
    version="2.0"
)

init_db()

HISTORICAL_EVENTS_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "ml",
    "dataset",
    "INDIA_TARGET_REGIONS_MAP.csv",
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


class LiveRecordRequest(BaseModel):
    captured_at: str | None = Field(default=None, max_length=80)
    session_id: str | None = Field(default=None, max_length=100)
    correlation_id: str | None = Field(default=None, max_length=100)
    trigger: str = Field(default="map-click", max_length=40)
    location_name: str = Field(default="Selected map location", max_length=300)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    risk_level: str = Field(min_length=1, max_length=20)
    risk_percentage: float | None = Field(default=None, ge=0, le=100)
    rainfall_1d_mm: float | None = Field(default=None, ge=0, le=2000)
    rainfall_3d_mm: float | None = Field(default=None, ge=0, le=3000)
    rainfall_7d_mm: float | None = Field(default=None, ge=0, le=4000)
    soil_moisture_0_7cm: float | None = Field(default=None, ge=0, le=1)
    elevation_m: float | None = Field(default=None, ge=-500, le=9000)
    slope_deg: float | None = Field(default=None, ge=0, le=90)
    raw_result: dict[str, Any] = Field(default_factory=dict)


def _get_nasa_power_daily_environment(latitude: float, longitude: float):
    end_date = date.today()
    start_date = end_date - timedelta(days=21)

    try:
        response = requests.get(
            "https://power.larc.nasa.gov/api/temporal/daily/point",
            params={
                "parameters": "PRECTOTCORR,GWETTOP",
                "community": "AG",
                "longitude": longitude,
                "latitude": latitude,
                "start": start_date.strftime("%Y%m%d"),
                "end": end_date.strftime("%Y%m%d"),
                "format": "JSON",
            },
            timeout=30,
        )
        response.raise_for_status()
        parameters = response.json()["properties"]["parameter"]
        rainfall_by_day = parameters["PRECTOTCORR"]
        soil_moisture_by_day = parameters["GWETTOP"]
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Live weather is rate-limited and NASA POWER backup data is unavailable.",
        ) from exc

    readings = []
    for date_key, rainfall_value in rainfall_by_day.items():
        try:
            rainfall = float(rainfall_value)
            soil_moisture = float(soil_moisture_by_day[date_key])
            observation_date = datetime.strptime(date_key, "%Y%m%d").date()
        except (KeyError, TypeError, ValueError):
            continue

        if (
            not math.isfinite(rainfall)
            or not math.isfinite(soil_moisture)
            or rainfall < 0
            or not 0 <= soil_moisture <= 1
        ):
            continue

        readings.append((observation_date, rainfall, soil_moisture))

    readings.sort(key=lambda reading: reading[0])
    recent_readings = readings[-7:]
    if (
        len(recent_readings) < 7
        or (recent_readings[-1][0] - recent_readings[0][0]).days != 6
    ):
        raise HTTPException(
            status_code=503,
            detail="Live weather is rate-limited and NASA POWER has insufficient recent data.",
        )

    daily_rainfall = [
        {"date": day.isoformat(), "rainfall_mm": round(rainfall, 2)}
        for day, rainfall, _ in recent_readings
    ]
    return {
        "latitude": latitude,
        "longitude": longitude,
        "rainfall_1d_mm": round(recent_readings[-1][1], 2),
        "rainfall_3d_mm": round(sum(reading[1] for reading in recent_readings[-3:]), 2),
        "rainfall_7d_mm": round(sum(reading[1] for reading in recent_readings), 2),
        "soil_moisture_0_7cm": round(recent_readings[-1][2], 3),
        "elevation_m": None,
        "rainfall_daily": daily_rainfall,
        "data_source": "NASA POWER",
        "observed_through": recent_readings[-1][0].isoformat(),
        "is_live_data": False,
    }


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
# LIVE RECORDS
# ============================================================

@app.get("/historical-events")
def get_historical_events():
    try:
        with open(HISTORICAL_EVENTS_CSV, newline="", encoding="utf-8-sig") as catalog_file:
            events = []
            for row in csv.DictReader(catalog_file):
                try:
                    latitude = float(row["latitude"])
                    longitude = float(row["longitude"])
                except (KeyError, TypeError, ValueError):
                    continue

                events.append(
                    {
                        "event_id": row.get("event_id"),
                        "event_date": row.get("event_date"),
                        "event_title": row.get("event_title"),
                        "location": row.get("location"),
                        "latitude": latitude,
                        "longitude": longitude,
                        "state": row.get("state"),
                        "category": row.get("landslide_category"),
                        "trigger": row.get("landslide_trigger"),
                        "size": row.get("landslide_size"),
                    }
                )
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail="Historical event catalog is unavailable.",
        ) from exc

    return {"events": events, "count": len(events)}

@app.get("/records")
def get_records(limit: int = Query(default=50, ge=1, le=200)):
    return {"records": list_records(limit)}


@app.get("/records/{record_id}")
def get_record_by_id(record_id: str):
    record = get_record(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Live record not found")
    return record


@app.post("/records", status_code=201)
def add_record(data: LiveRecordRequest):
    record = data.model_dump()
    record["client_captured_at"] = record.pop("captured_at")
    return create_record(record)


@app.delete("/records")
def clear_records():
    delete_all_records()
    return {"deleted": True}


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
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to retrieve live environmental data: {exc}"
        )

    if response.status_code == 429:
        return _get_nasa_power_daily_environment(latitude, longitude)

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Open-Meteo error {response.status_code}: {response.text}"
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
        "data_source": "Open-Meteo",
        "observed_through": times[-1] if times else None,
        "is_live_data": True,
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

        "provenance": {
            "weather": {
                "provider": "Open-Meteo",
                "endpoint": "https://api.open-meteo.com/v1/forecast",
                "past_days": 7,
                "forecast_days": 0,
            },
            "elevation": {
                "provider": "Open-Meteo",
                "endpoint": "https://api.open-meteo.com/v1/elevation",
                "grid_points": 9,
            },
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


@app.get("/risk-grid")
def get_risk_grid(
    bbox: str | None = None,
    limit: int = Query(default=2000, ge=1, le=10000),
):
    try:
        parsed_bbox = parse_bbox(bbox)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return get_risk_grid_geojson(parsed_bbox, limit)


@app.get("/exposure")
def get_exposure(
    bbox: str,
    limit: int = Query(default=2000, ge=1, le=10000),
):
    try:
        parsed_bbox = parse_bbox(bbox)
        return get_exposure_geojson(parsed_bbox, limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/replay")
def get_replay(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    event_date: date = Query(alias="date"),
    days: int = Query(default=7, ge=1, le=30),
):
    if event_date >= date.today():
        raise HTTPException(status_code=422, detail="date must be before today")
    try:
        return replay_location(latitude, longitude, event_date, days=days)
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Historical replay data unavailable: {type(exc).__name__}",
        ) from exc