import json
from itertools import islice
import logging
import math
import os
import time
from pathlib import Path
from typing import Any, Iterator
from datetime import datetime, timedelta, timezone

import requests
from pyproj import CRS, Transformer
from shapely.geometry import box, mapping, shape
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree

from backend import record_store
from backend.ml_predictor import model_is_loaded, predict_risk


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_BOUNDARIES_PATH = PROJECT_ROOT / "ml" / "dataset" / "target_states.geojson"
DISTRICT_BOUNDARIES_PATH = PROJECT_ROOT / "ml" / "dataset" / "district_boundaries.geojson"
TARGET_STATE_NAMES = frozenset(
    {
        "Arunachal Pradesh",
        "Assam",
        "Manipur",
        "Meghalaya",
        "Mizoram",
        "Nagaland",
        "Sikkim",
        "Tripura",
    }
)
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
logger = logging.getLogger(__name__)


def load_grid_boundaries(
    state_path: Path = STATE_BOUNDARIES_PATH,
    district_path: Path = DISTRICT_BOUNDARIES_PATH,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with state_path.open(encoding="utf-8") as source:
        state_features = json.load(source).get("features", [])
    with district_path.open(encoding="utf-8") as source:
        district_features = json.load(source).get("features", [])

    return state_features, district_features


def _match_district(
    point: Any,
    cell_geometry: Any,
    districts: list[dict[str, Any]],
    district_geometries: list[Any],
    district_tree: STRtree,
) -> dict[str, Any] | None:
    point_matches = [
        int(index)
        for index in district_tree.query(point, predicate="intersects")
        if district_geometries[int(index)].covers(point)
    ]
    if len(point_matches) == 1:
        return districts[point_matches[0]]
    if point_matches:
        return None

    overlaps = []
    for index in district_tree.query(cell_geometry, predicate="intersects"):
        district_index = int(index)
        overlap_area = district_geometries[district_index].intersection(
            cell_geometry
        ).area
        if overlap_area > 0:
            overlaps.append((overlap_area, district_index))
    if not overlaps:
        return None

    overlaps.sort(reverse=True)
    best_area, best_index = overlaps[0]
    if best_area < cell_geometry.area * 0.5:
        return None
    if len(overlaps) > 1 and math.isclose(best_area, overlaps[1][0], rel_tol=1e-9):
        return None
    return districts[best_index]


def generate_grid_cells(
    state_features: list[dict[str, Any]],
    district_features: list[dict[str, Any]],
    cell_size_m: int = 1000,
    target_state_names: frozenset[str] = TARGET_STATE_NAMES,
) -> Iterator[dict[str, Any]]:
    if cell_size_m < 100 or cell_size_m > 100_000:
        raise ValueError("cell_size_m must be between 100 and 100000 metres")

    state_geometries = {
        feature["properties"]["name"]: shape(feature["geometry"])
        for feature in state_features
        if feature.get("properties", {}).get("admin") == "India"
        and feature.get("properties", {}).get("name") in target_state_names
        and feature.get("geometry")
    }
    missing_states = target_state_names - state_geometries.keys()
    if missing_states:
        raise ValueError(
            "Target-state polygons missing: " + ", ".join(sorted(missing_states))
        )

    geographic_region = unary_union(list(state_geometries.values()))
    center = geographic_region.centroid
    local_crs = CRS.from_proj4(
        f"+proj=aeqd +lat_0={center.y} +lon_0={center.x} "
        "+datum=WGS84 +units=m +no_defs"
    )
    geographic_crs = CRS.from_epsg(4326)
    project = Transformer.from_crs(
        geographic_crs, local_crs, always_xy=True
    ).transform
    unproject = Transformer.from_crs(
        local_crs, geographic_crs, always_xy=True
    ).transform

    projected_states = {
        name: transform(project, geometry)
        for name, geometry in state_geometries.items()
    }
    projected_region = unary_union(list(projected_states.values()))

    districts = []
    for feature in district_features:
        properties = feature.get("properties", {})
        if (
            properties.get("shapeGroup") != "IND"
            or properties.get("shapeType") != "ADM2"
            or not feature.get("geometry")
        ):
            continue

        geographic_geometry = shape(feature["geometry"])
        representative_point = geographic_geometry.representative_point()
        matching_states = [
            name
            for name, geometry in state_geometries.items()
            if geometry.covers(representative_point)
        ]
        if len(matching_states) != 1:
            continue

        districts.append(
            {
                "name": properties.get("shapeName"),
                "state": matching_states[0],
                "geometry": transform(project, geographic_geometry),
            }
        )

    if not districts:
        raise ValueError("No India ADM2 district polygons matched the target states")

    district_geometries = [district["geometry"] for district in districts]
    district_tree = STRtree(district_geometries)
    min_x, min_y, max_x, max_y = projected_region.bounds
    first_column = math.floor(min_x / cell_size_m)
    last_column = math.ceil(max_x / cell_size_m) - 1
    first_row = math.floor(min_y / cell_size_m)
    last_row = math.ceil(max_y / cell_size_m) - 1

    for row in range(first_row, last_row + 1):
        y_min = row * cell_size_m
        for column in range(first_column, last_column + 1):
            x_min = column * cell_size_m
            clipped_geometry = box(
                x_min,
                y_min,
                x_min + cell_size_m,
                y_min + cell_size_m,
            ).intersection(projected_region)
            if clipped_geometry.is_empty:
                continue

            point = clipped_geometry.representative_point()
            district = _match_district(
                point,
                clipped_geometry,
                districts,
                district_geometries,
                district_tree,
            )
            state_name = district["state"] if district else next(
                (
                    name
                    for name, geometry in projected_states.items()
                    if geometry.covers(point)
                ),
                None,
            )
            longitude, latitude = unproject(point.x, point.y)

            yield {
                "cell_id": f"{cell_size_m}:{row}:{column}",
                "latitude": float(latitude),
                "longitude": float(longitude),
                "district": district["name"] if district else None,
                "state": state_name,
                "grid_size_m": cell_size_m,
                "geometry": mapping(transform(unproject, clipped_geometry)),
            }


def _parse_environment(location: dict[str, Any]) -> dict[str, float | str | None]:
    hourly = location.get("hourly", {})
    precipitation = hourly.get("precipitation", [])
    soil_moisture = hourly.get("soil_moisture_0_to_7cm", [])
    if len(precipitation) < 24:
        raise ValueError("Open-Meteo returned fewer than 24 rainfall observations")

    def rainfall_total(hours: int) -> float:
        readings = [value for value in precipitation[-hours:] if value is not None]
        if not readings:
            raise ValueError("Open-Meteo returned no usable rainfall observations")
        return round(sum(float(value) for value in readings), 2)

    valid_soil = [value for value in soil_moisture[-168:] if value is not None]
    if not valid_soil:
        raise ValueError("Open-Meteo returned no usable soil-moisture observations")

    elevation = location.get("elevation")
    if isinstance(elevation, list):
        elevation = elevation[0] if elevation else None
    if elevation is None:
        raise ValueError("Open-Meteo returned no elevation for a grid cell")

    return {
        "rainfall_1d_mm": rainfall_total(24),
        "rainfall_3d_mm": rainfall_total(72),
        "rainfall_7d_mm": rainfall_total(168),
        "soil_moisture_0_7cm": round(float(valid_soil[-1]), 3),
        "elevation_m": float(elevation),
        "observed_through": (
            hourly.get("time", [])[-1] if hourly.get("time") else None
        ),
    }


def _fetch_weather_batch(
    cells: list[dict[str, Any]],
    request_get: Any = None,
    retry_delay_seconds: float = 1.0,
    max_attempts: int = 3,
) -> list[dict[str, Any]]:
    request_get = request_get or requests.get
    params = {
        "latitude": ",".join(f"{cell['latitude']:.5f}" for cell in cells),
        "longitude": ",".join(f"{cell['longitude']:.5f}" for cell in cells),
        "hourly": "precipitation,soil_moisture_0_to_7cm",
        "past_days": 7,
        "forecast_days": 0,
        "timezone": "UTC",
    }

    for attempt in range(max_attempts):
        try:
            response = request_get(OPEN_METEO_FORECAST_URL, params=params, timeout=45)
            status_code = getattr(response, "status_code", 200)
            if status_code == 429 or status_code >= 500:
                if attempt + 1 == max_attempts:
                    response.raise_for_status()
                    raise requests.HTTPError(f"Open-Meteo returned HTTP {status_code}")
                retry_after = getattr(response, "headers", {}).get("Retry-After")
                try:
                    delay = max(float(retry_after), 0.0) if retry_after else retry_delay_seconds * (2**attempt)
                except ValueError:
                    delay = retry_delay_seconds * (2**attempt)
                time.sleep(delay)
                continue

            response.raise_for_status()
            payload = response.json()
            locations = payload if isinstance(payload, list) else [payload]
            if len(locations) != len(cells):
                raise ValueError(
                    f"Open-Meteo returned {len(locations)} locations for {len(cells)} cells"
                )
            return [_parse_environment(location) for location in locations]
        except requests.RequestException:
            if attempt + 1 == max_attempts:
                raise
            time.sleep(retry_delay_seconds * (2**attempt))

    raise requests.RequestException("Open-Meteo batch failed after retries")


def _iter_cell_batches(
    cells: Iterator[dict[str, Any]], batch_size: int
) -> Iterator[list[dict[str, Any]]]:
    while batch := list(islice(cells, batch_size)):
        yield batch


def run_grid_update(
    cell_size_m: int = 1000,
    batch_size: int = 200,
    cache_hours: float = 4,
    request_interval_seconds: float = 2,
    max_cells: int | None = None,
    persist: bool = True,
    request_get: Any = None,
) -> dict[str, Any]:
    if not 1 <= batch_size <= 200:
        raise ValueError("batch_size must be between 1 and 200")
    if cache_hours < 0:
        raise ValueError("cache_hours must not be negative")
    if max_cells is not None and max_cells < 1:
        raise ValueError("max_cells must be positive")
    if not model_is_loaded():
        raise RuntimeError("The saved landslide model is not loaded; grid scoring stopped")

    state_features, district_features = load_grid_boundaries()
    cells_iterator: Iterator[dict[str, Any]] = generate_grid_cells(
        state_features, district_features, cell_size_m
    )
    if max_cells is not None:
        cells_iterator = iter(islice(cells_iterator, max_cells))

    run_started = datetime.now(timezone.utc)
    fresh_after = (run_started - timedelta(hours=cache_hours)).isoformat()

    generated_cells = cached_cells = updated_cells = failed_cells = 0
    unassigned_cells = 0
    pending: list[dict[str, Any]] = []
    preview: list[dict[str, Any]] = []
    last_request_at: float | None = None

    def update_batch(batch: list[dict[str, Any]]) -> None:
        nonlocal updated_cells, failed_cells, last_request_at
        if not batch:
            return
        if last_request_at is not None:
            wait_seconds = request_interval_seconds - (time.monotonic() - last_request_at)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
        try:
            environments = _fetch_weather_batch(batch, request_get=request_get)
            last_request_at = time.monotonic()
            stored_cells = []
            for cell, environment in zip(batch, environments):
                prediction = predict_risk(
                    rainfall_1d_mm=environment["rainfall_1d_mm"],
                    rainfall_3d_mm=environment["rainfall_3d_mm"],
                    rainfall_7d_mm=environment["rainfall_7d_mm"],
                    soil_moisture_0_7cm=environment["soil_moisture_0_7cm"],
                    elevation_m=environment["elevation_m"],
                    slope_deg=0.0,
                )
                result = {
                    **cell,
                    "risk_score": float(prediction["risk_percentage"]),
                    "risk_band": prediction["risk_level"],
                    "inputs": {
                        key: environment[key]
                        for key in (
                            "rainfall_1d_mm",
                            "rainfall_3d_mm",
                            "rainfall_7d_mm",
                            "soil_moisture_0_7cm",
                            "elevation_m",
                        )
                    },
                    "updated_at": run_started.isoformat(),
                }
                result["inputs"]["source"] = "Open-Meteo"
                result["inputs"]["observed_through"] = environment["observed_through"]
                if not persist:
                    preview.append(
                        {
                            "cell_id": cell["cell_id"],
                            "latitude": cell["latitude"],
                            "longitude": cell["longitude"],
                            "district": cell["district"],
                            "state": cell["state"],
                            "risk_score": result["risk_score"],
                            "risk_band": result["risk_band"],
                            "inputs": result["inputs"],
                        }
                    )
                stored_cells.append(result)
            if persist:
                record_store.save_risk_grid_cells(stored_cells)
            updated_cells += len(stored_cells)
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            failed_cells += len(batch)
            logger.warning("Risk-grid batch of %d cells failed: %s", len(batch), exc)

    for candidate_batch in _iter_cell_batches(cells_iterator, max(batch_size, 500)):
        generated_cells += len(candidate_batch)
        if persist and cache_hours > 0:
            fresh_ids = record_store.get_fresh_risk_grid_cell_ids(
                [cell["cell_id"] for cell in candidate_batch],
                cell_size_m,
                fresh_after,
            )
        else:
            fresh_ids = set()
        for cell in candidate_batch:
            if cell["district"] is None:
                unassigned_cells += 1
            if cell["cell_id"] in fresh_ids:
                cached_cells += 1
                continue
            pending.append(cell)
            if len(pending) >= batch_size:
                update_batch(pending)
                pending = []
    update_batch(pending)

    if generated_cells == 0:
        raise ValueError("No grid cells were generated for the selected target region")

    complete = max_cells is None and failed_cells == 0
    finished_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "grid_size_m": cell_size_m,
        "generated_cells": generated_cells,
        "updated_cells": updated_cells,
        "cached_cells": cached_cells,
        "failed_cells": failed_cells,
        "district_unassigned_cells": unassigned_cells,
        "complete": complete,
        "run_started_at": run_started.isoformat(),
        "run_finished_at": finished_at,
        "preview": not persist,
        "sample_results": preview,
    }
    if persist:
        record_store.set_risk_grid_metadata(summary)
    logger.info(
        "Risk grid %dm: generated=%d updated=%d cached=%d failed=%d complete=%s",
        cell_size_m,
        generated_cells,
        updated_cells,
        cached_cells,
        failed_cells,
        complete,
    )
    return summary


def parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if bbox is None:
        return None
    try:
        values = tuple(float(value.strip()) for value in bbox.split(","))
    except ValueError as exc:
        raise ValueError("bbox must contain four numeric values") from exc
    if len(values) != 4:
        raise ValueError("bbox must be min_lon,min_lat,max_lon,max_lat")
    min_lon, min_lat, max_lon, max_lat = values
    if not all(math.isfinite(value) for value in values):
        raise ValueError("bbox values must be finite")
    if not (-180 <= min_lon < max_lon <= 180):
        raise ValueError("bbox longitude bounds are invalid")
    if not (-90 <= min_lat < max_lat <= 90):
        raise ValueError("bbox latitude bounds are invalid")
    return min_lon, min_lat, max_lon, max_lat


def get_risk_grid_geojson(
    bbox: tuple[float, float, float, float] | None, limit: int
) -> dict[str, Any]:
    metadata = record_store.get_risk_grid_metadata()
    if metadata is None:
        return {
            "type": "FeatureCollection",
            "features": [],
            "count": 0,
            "grid_size_m": None,
            "last_updated": None,
            "complete": False,
            "district_summary": [],
        }

    grid_size_m = int(metadata["grid_size_m"])
    cells = record_store.get_risk_grid_cells(grid_size_m, bbox, limit)
    features = [
        {
            "type": "Feature",
            "id": cell["cell_id"],
            "geometry": cell["geometry"],
            "properties": {
                "cell_id": cell["cell_id"],
                "latitude": cell["latitude"],
                "longitude": cell["longitude"],
                "district": cell["district"],
                "state": cell["state"],
                "risk_score": cell["risk_score"],
                "risk_band": cell["risk_band"],
                "inputs": cell["inputs"],
                "updated_at": cell["updated_at"],
                "grid_size_m": cell["grid_size_m"],
            },
        }
        for cell in cells
    ]
    return {
        "type": "FeatureCollection",
        "features": features,
        "count": len(features),
        "grid_size_m": grid_size_m,
        "last_updated": record_store.get_risk_grid_last_updated(grid_size_m),
        "complete": bool(metadata.get("complete", False)),
        "generated_cells": int(metadata.get("generated_cells", 0)),
        "cached_cells": int(metadata.get("cached_cells", 0)),
        "failed_cells": int(metadata.get("failed_cells", 0)),
        "district_unassigned_cells": int(
            metadata.get("district_unassigned_cells", 0)
        ),
        "district_summary": record_store.get_risk_grid_district_summary(
            grid_size_m, limit=10
        ),
    }