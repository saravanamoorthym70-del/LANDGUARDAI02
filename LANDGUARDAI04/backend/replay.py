import logging
import math
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable

import requests

from backend.ml_predictor import predict_risk


OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
HISTORICAL_HOURLY_VARIABLES = "precipitation,soil_moisture_0_to_7cm"
logger = logging.getLogger(__name__)


def fetch_historical_weather(
    latitude: float,
    longitude: float,
    event_date: date,
    days: int = 7,
    request_get: Callable[..., Any] | None = None,
    retry_delay_seconds: float = 1.0,
    max_attempts: int = 3,
) -> dict[str, Any]:
    first_replay_day = event_date - timedelta(days=days)
    start_date = first_replay_day - timedelta(days=6)
    end_date = event_date - timedelta(days=1)
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "hourly": HISTORICAL_HOURLY_VARIABLES,
        "timezone": "UTC",
    }
    request_get = request_get or requests.get
    for attempt in range(max_attempts):
        try:
            response = request_get(
                OPEN_METEO_ARCHIVE_URL,
                params=params,
                timeout=45,
            )
            status_code = getattr(response, "status_code", 200)
            if status_code == 429 or status_code >= 500:
                if attempt + 1 == max_attempts:
                    response.raise_for_status()
                retry_after = getattr(response, "headers", {}).get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else retry_delay_seconds * (2**attempt)
                except ValueError:
                    delay = retry_delay_seconds * (2**attempt)
                time.sleep(max(delay, 0.0))
                continue
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                raise ValueError(payload.get("reason", "Historical API returned an error"))
            return payload
        except requests.RequestException:
            if attempt + 1 == max_attempts:
                raise
            time.sleep(retry_delay_seconds * (2**attempt))
    raise requests.RequestException("Historical Open-Meteo request failed after retries")


def fetch_elevation(
    latitude: float,
    longitude: float,
    request_get: Callable[..., Any] | None = None,
) -> float:
    request_get = request_get or requests.get
    response = request_get(
        OPEN_METEO_ELEVATION_URL,
        params={"latitude": latitude, "longitude": longitude},
        timeout=30,
    )
    response.raise_for_status()
    value = response.json().get("elevation")
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None or not math.isfinite(float(value)):
        raise ValueError("Open-Meteo did not return usable elevation")
    return float(value)


def score_daily_replay(
    latitude: float,
    longitude: float,
    event_date: date,
    hourly: dict[str, list[Any]],
    elevation_m: float,
    days: int = 7,
    scorer: Callable[..., dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not 1 <= days <= 30:
        raise ValueError("days must be between 1 and 30")
    if not math.isfinite(float(elevation_m)):
        raise ValueError("elevation_m must be finite")
    times = hourly.get("time", [])
    precipitation = hourly.get("precipitation", [])
    soil_moisture = hourly.get("soil_moisture_0_to_7cm", [])
    if len(times) != len(precipitation) or len(times) != len(soil_moisture):
        raise ValueError("Historical API returned misaligned hourly arrays")

    parsed_dates = []
    for time_value in times:
        try:
            parsed_dates.append(datetime.fromisoformat(str(time_value)).date())
        except ValueError:
            parsed_dates.append(None)

    daily_scores = []
    scorer = scorer or predict_risk
    for days_before in range(days, 0, -1):
        score_date = event_date - timedelta(days=days_before)
        day_indices = [index for index, value in enumerate(parsed_dates) if value == score_date]
        if not day_indices:
            daily_scores.append(
                {"date": score_date.isoformat(), "risk_score": None, "risk_band": "UNAVAILABLE"}
            )
            continue

        end_index = day_indices[-1]
        window_start = max(0, end_index - 167)
        rain_window = precipitation[window_start : end_index + 1]
        soil_window = soil_moisture[window_start : end_index + 1]

        def rainfall_total(hour_count: int) -> float:
            values = [
                float(value)
                for value in precipitation[max(0, end_index - hour_count + 1) : end_index + 1]
                if value is not None
            ]
            if not values:
                raise ValueError("No rainfall observations in requested window")
            return float(sum(values))

        valid_soil = [float(value) for value in soil_window if value is not None]
        if len(rain_window) < 168 or not valid_soil:
            daily_scores.append(
                {"date": score_date.isoformat(), "risk_score": None, "risk_band": "UNAVAILABLE"}
            )
            continue

        try:
            result = scorer(
                rainfall_1d_mm=round(rainfall_total(24), 2),
                rainfall_3d_mm=round(rainfall_total(72), 2),
                rainfall_7d_mm=round(rainfall_total(168), 2),
                soil_moisture_0_7cm=valid_soil[-1],
                elevation_m=float(elevation_m),
                slope_deg=0.0,
            )
        except (TypeError, ValueError):
            daily_scores.append(
                {"date": score_date.isoformat(), "risk_score": None, "risk_band": "UNAVAILABLE"}
            )
            continue

        score = result.get("risk_percentage")
        if score is None or not math.isfinite(float(score)):
            daily_scores.append(
                {"date": score_date.isoformat(), "risk_score": None, "risk_band": "UNAVAILABLE"}
            )
            continue
        daily_scores.append(
            {
                "date": score_date.isoformat(),
                "risk_score": float(score),
                "risk_band": str(result["risk_level"]),
                "risk_probability": float(result.get("risk_probability", float(score) / 100)),
            }
        )

    return daily_scores


def replay_location(
    latitude: float,
    longitude: float,
    event_date: date,
    days: int = 7,
    elevation_m: float | None = None,
    request_get: Callable[..., Any] | None = None,
    scorer: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    history = fetch_historical_weather(
        latitude,
        longitude,
        event_date,
        days=days,
        request_get=request_get,
    )
    if elevation_m is None:
        elevation_m = history.get("elevation")
    if elevation_m is None:
        elevation_m = fetch_elevation(latitude, longitude, request_get=request_get)
    hourly = history.get("hourly", {})
    daily_scores = score_daily_replay(
        latitude,
        longitude,
        event_date,
        hourly,
        float(elevation_m),
        days=days,
        scorer=scorer,
    )
    metadata = {
        "provider": "Open-Meteo Historical Weather API",
        "endpoint": OPEN_METEO_ARCHIVE_URL,
        "weather_model_selection": "provider default, matching historical-event training fetch",
        "soil_moisture_variable": "soil_moisture_0_to_7cm",
        "observed_through": hourly.get("time", [None])[-1] if hourly.get("time") else None,
    }
    return {
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "elevation_m": float(elevation_m),
        },
        "event_date": event_date.isoformat(),
        "days": days,
        "daily_scores": daily_scores,
        "source": metadata,
        "score_semantics": "prototype screening score; not a calibrated event probability",
    }