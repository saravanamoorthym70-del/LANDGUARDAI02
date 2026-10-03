import json
import math
from pathlib import Path
from typing import Any, Callable

from shapely.geometry import box, mapping, shape
from shapely.strtree import STRtree

from backend import record_store


PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPOSURE_GPKG_PATH = PROJECT_ROOT / "ml" / "dataset" / "exposure_layers.gpkg"
EXPOSURE_CATEGORIES = (
    "roads",
    "bridges",
    "settlements",
    "schools",
    "hospitals",
    "railways",
)
POINT_EXPOSURE_CATEGORIES = ("settlements", "schools", "hospitals", "railways")


def _clean_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def read_exposure_layers(
    bbox: tuple[float, float, float, float],
    limit: int,
    gpkg_path: Path = EXPOSURE_GPKG_PATH,
) -> dict[str, list[dict[str, Any]]]:
    if not gpkg_path.exists():
        raise FileNotFoundError(
            f"Exposure GeoPackage not found at {gpkg_path}; "
            "run python -m ml.scripts.build_exposure_data"
        )

    try:
        import pyogrio
    except ImportError as exc:
        raise RuntimeError("Install pyogrio to serve the exposure overlay") from exc

    available_layers = {str(row[0]) for row in pyogrio.list_layers(gpkg_path)}
    result = {}
    for category in EXPOSURE_CATEGORIES:
        features = []
        source_layers = [category]
        if category in POINT_EXPOSURE_CATEGORIES:
            source_layers.append(f"{category}_points")
        for source_layer in source_layers:
            if source_layer not in available_layers:
                continue
            frame = pyogrio.read_dataframe(
                gpkg_path,
                layer=source_layer,
                bbox=bbox,
            )
            frame = frame.loc[frame.geometry.notna() & ~frame.geometry.is_empty]
            for _, row in frame.head(limit).iterrows():
                properties = {
                    key: _clean_value(value)
                    for key, value in row.items()
                    if key != frame.geometry.name
                }
                features.append(
                    {
                        "type": "Feature",
                        "id": properties.get("feature_id"),
                        "geometry": mapping(row.geometry),
                        "properties": properties,
                    }
                )
        result[category] = features
    return result


def intersect_high_cells(
    high_cells: list[dict[str, Any]],
    layer_features: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    matched_by_category: dict[str, dict[str, dict[str, Any]]] = {
        category: {} for category in EXPOSURE_CATEGORIES
    }
    high_cell_results = []
    cell_intersections = [
        {category: [] for category in EXPOSURE_CATEGORIES}
        for _ in high_cells
    ]
    cell_geometries = [shape(cell["geometry"]) for cell in high_cells]

    for category in EXPOSURE_CATEGORIES:
        features = layer_features.get(category, [])
        valid_features = [
            (feature, shape(feature["geometry"]))
            for feature in features
            if feature.get("geometry")
        ]
        if not valid_features:
            continue

        valid_features_list = [feature for feature, _ in valid_features]
        tree = STRtree([geometry for _, geometry in valid_features])
        for cell_index, cell_geometry in enumerate(cell_geometries):
            matched = []
            for index in tree.query(cell_geometry, predicate="intersects"):
                feature = valid_features_list[int(index)]
                feature_id = str(
                    feature.get("id")
                    or feature.get("properties", {}).get("feature_id")
                    or f"{category}:{index}"
                )
                matched_by_category[category][feature_id] = feature
                matched.append(feature_id)
            cell_intersections[cell_index][category] = sorted(set(matched))

    for cell, intersections in zip(high_cells, cell_intersections):
        high_cell_results.append(
            {
                "cell_id": cell["cell_id"],
                "latitude": cell["latitude"],
                "longitude": cell["longitude"],
                "district": cell.get("district"),
                "state": cell.get("state"),
                "risk_score": cell["risk_score"],
                "intersections": intersections,
            }
        )

    layers = {
        category: {
            "type": "FeatureCollection",
            "features": list(matched_by_category[category].values()),
        }
        for category in EXPOSURE_CATEGORIES
    }
    counts = {
        category: len(matched_by_category[category])
        for category in EXPOSURE_CATEGORIES
    }
    named_roads = []
    for feature in layers["roads"]["features"]:
        properties = feature.get("properties", {})
        highway = str(properties.get("highway") or "").lower()
        if highway in {"motorway", "trunk", "primary", "secondary"}:
            name = properties.get("name") or properties.get("ref")
            if name and str(name) not in named_roads:
                named_roads.append(str(name))
    road_summary = (
        f"Highway section {named_roads[0]}"
        if named_roads
        else f"{counts['roads']} mapped road sections"
    )
    summary = {
        "high_cells": len(high_cells),
        "roads": counts["roads"],
        "bridges": counts["bridges"],
        "settlements": counts["settlements"],
        "schools": counts["schools"],
        "hospitals": counts["hospitals"],
        "railways": counts["railways"],
        "headline": (
            f"{road_summary} and {counts['settlements']} mapped settlements "
            f"intersect {len(high_cells)} HIGH cells."
        ),
    }
    return {"summary": summary, "layers": layers, "high_cells": high_cell_results}


def get_exposure_geojson(
    bbox: tuple[float, float, float, float],
    limit: int = 5000,
    layer_reader: Callable[..., dict[str, list[dict[str, Any]]]] = read_exposure_layers,
    high_cell_reader: Callable[..., list[dict[str, Any]]] = record_store.list_high_risk_grid_cells,
) -> dict[str, Any]:
    min_lon, min_lat, max_lon, max_lat = bbox
    high_cells = high_cell_reader(bbox, limit)
    clipped_bbox = box(min_lon, min_lat, max_lon, max_lat)
    high_cells = [
        cell
        for cell in high_cells
        if shape(cell["geometry"]).intersects(clipped_bbox)
    ]
    if not high_cells:
        return intersect_high_cells(
            [], {category: [] for category in EXPOSURE_CATEGORIES}
        )
    layer_features = layer_reader(bbox, limit)
    return intersect_high_cells(high_cells, layer_features)