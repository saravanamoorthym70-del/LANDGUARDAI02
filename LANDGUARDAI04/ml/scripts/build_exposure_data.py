"""Build clipped OSM exposure layers from regional Geofabrik PBF extracts."""

import argparse
import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely.geometry import shape

from backend.risk_grid import load_grid_boundaries, TARGET_STATE_NAMES


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = PROJECT_ROOT / "ml" / "dataset" / "exposure_layers.gpkg"
POINT_CATEGORIES = ("settlements_points", "schools_points", "hospitals_points", "railways_points")
HSTORE_TAG = re.compile(r'"((?:[^"\\]|\\.)*)"=>"((?:[^"\\]|\\.)*)"')
LOGGER = logging.getLogger(__name__)


def parse_other_tags(raw_tags: Any) -> dict[str, str]:
    if not isinstance(raw_tags, str):
        return {}
    return {
        key.replace('\\"', '"'): value.replace('\\"', '"')
        for key, value in HSTORE_TAG.findall(raw_tags)
    }


def _safe_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def _matches_bridge(value: str | None) -> bool:
    return bool(value and value.lower() not in {"no", "false", "0", "ford"})


def _feature_record(
    osm_id: Any,
    source_layer: str,
    geometry: Any,
    properties: dict[str, Any],
    boundary: Any,
) -> dict[str, Any] | None:
    if geometry is None or geometry.is_empty:
        return None
    clipped = geometry.intersection(boundary)
    if clipped.is_empty:
        return None
    feature_id = f"{source_layer}:{osm_id}"
    return {
        "feature_id": feature_id,
        "osm_id": str(osm_id),
        "source_layer": source_layer,
        "name": properties.get("name"),
        "highway": properties.get("highway"),
        "bridge": properties.get("bridge"),
        "railway": properties.get("railway"),
        "amenity": properties.get("amenity"),
        "place": properties.get("place"),
        "source": properties.get("source"),
        "geometry": clipped,
    }


def _append_record(
    output: dict[str, dict[str, dict[str, Any]]],
    category: str,
    record: dict[str, Any] | None,
) -> None:
    if record is not None:
        output[category][record["feature_id"]] = record


def collect_exposure_layers(
    pbf_paths: list[Path],
    state_features: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    from shapely.ops import unary_union

    states = [
        (feature["properties"]["name"], shape(feature["geometry"]))
        for feature in state_features
        if feature.get("properties", {}).get("admin") == "India"
        and feature.get("properties", {}).get("name") in TARGET_STATE_NAMES
        and feature.get("geometry")
    ]
    found_states = {name for name, _ in states}
    if found_states != TARGET_STATE_NAMES:
        raise ValueError(
            "Target state boundaries incomplete: "
            + ", ".join(sorted(TARGET_STATE_NAMES - found_states))
        )

    target_region = unary_union([geometry for _, geometry in states])
    bounds = tuple(float(value) for value in target_region.bounds)
    collected: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for pbf_path in pbf_paths:
        if not pbf_path.exists():
            raise FileNotFoundError(f"OSM PBF not found: {pbf_path}")
        extract_name = pbf_path.name
        road_lines = pyogrio.read_dataframe(
            pbf_path,
            layer="lines",
            columns=["osm_id", "name", "highway", "railway", "other_tags"],
            bbox=bounds,
        )
        for _, row in road_lines.iterrows():
            tags = parse_other_tags(row.get("other_tags"))
            properties = {
                "name": _safe_text(row.get("name")),
                "highway": _safe_text(row.get("highway")),
                "railway": _safe_text(row.get("railway")) or tags.get("railway"),
                "bridge": tags.get("bridge"),
                "source": extract_name,
            }
            if properties["highway"]:
                _append_record(
                    collected,
                    "roads",
                    _feature_record(row["osm_id"], "lines", row.geometry, properties, target_region),
                )
            if _matches_bridge(properties["bridge"]):
                _append_record(
                    collected,
                    "bridges",
                    _feature_record(row["osm_id"], "lines", row.geometry, properties, target_region),
                )
            if properties["railway"]:
                _append_record(
                    collected,
                    "railways",
                    _feature_record(row["osm_id"], "lines", row.geometry, properties, target_region),
                )
        LOGGER.info("%s: read %d lines", extract_name, len(road_lines))

        points = pyogrio.read_dataframe(
            pbf_path,
            layer="points",
            columns=["osm_id", "name", "place", "other_tags"],
            bbox=bounds,
        )
        for _, row in points.iterrows():
            tags = parse_other_tags(row.get("other_tags"))
            properties = {
                "name": _safe_text(row.get("name")),
                "place": _safe_text(row.get("place")) or tags.get("place"),
                "amenity": tags.get("amenity"),
                "healthcare": tags.get("healthcare"),
                "railway": tags.get("railway"),
                "source": extract_name,
            }
            if properties["place"]:
                _append_record(
                    collected,
                    "settlements_points",
                    _feature_record(row["osm_id"], "points", row.geometry, properties, target_region),
                )
            if properties["amenity"] == "school":
                _append_record(
                    collected,
                    "schools_points",
                    _feature_record(row["osm_id"], "points", row.geometry, properties, target_region),
                )
            if properties["amenity"] == "hospital" or properties["healthcare"] == "hospital":
                _append_record(
                    collected,
                    "hospitals_points",
                    _feature_record(row["osm_id"], "points", row.geometry, properties, target_region),
                )
            if properties["railway"]:
                _append_record(
                    collected,
                    "railways_points",
                    _feature_record(row["osm_id"], "points", row.geometry, properties, target_region),
                )
        LOGGER.info("%s: read %d points", extract_name, len(points))

        feature_frames = [
            pyogrio.read_dataframe(
                pbf_path,
                layer="multipolygons",
                columns=["osm_id", "name", "place", "amenity", "landuse", "other_tags"],
                bbox=bounds,
                where=where,
            )
            for where in (
                "place IS NOT NULL",
                "landuse = 'residential'",
                "amenity IS NOT NULL",
            )
        ]
        features = pd.concat(feature_frames, ignore_index=True).drop_duplicates("osm_id")
        for _, row in features.iterrows():
            tags = parse_other_tags(row.get("other_tags"))
            properties = {
                "name": _safe_text(row.get("name")),
                "place": _safe_text(row.get("place")) or tags.get("place"),
                "amenity": _safe_text(row.get("amenity")) or tags.get("amenity"),
                "healthcare": tags.get("healthcare"),
                "railway": tags.get("railway"),
                "source": extract_name,
            }
            landuse = _safe_text(row.get("landuse"))
            if properties["place"] or landuse == "residential":
                _append_record(
                    collected,
                    "settlements",
                    _feature_record(row["osm_id"], "multipolygons", row.geometry, properties, target_region),
                )
            if properties["amenity"] == "school":
                _append_record(
                    collected,
                    "schools",
                    _feature_record(row["osm_id"], "multipolygons", row.geometry, properties, target_region),
                )
            if properties["amenity"] == "hospital" or properties["healthcare"] == "hospital":
                _append_record(
                    collected,
                    "hospitals",
                    _feature_record(row["osm_id"], "multipolygons", row.geometry, properties, target_region),
                )
        LOGGER.info("%s: read %d filtered multipolygons", extract_name, len(features))

    categories = ("roads", "bridges", "settlements", "schools", "hospitals", "railways")
    return {
        category: list(collected[category].values())
        for category in (*categories, *POINT_CATEGORIES)
    }


def collect_exposure_point_layers(
    pbf_paths: list[Path],
    state_features: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    states = [
        (feature["properties"]["name"], shape(feature["geometry"]))
        for feature in state_features
        if feature.get("properties", {}).get("admin") == "India"
        and feature.get("properties", {}).get("name") in TARGET_STATE_NAMES
        and feature.get("geometry")
    ]
    if {name for name, _ in states} != TARGET_STATE_NAMES:
        raise ValueError("Target-state boundary collection is incomplete")

    collected: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for pbf_path in pbf_paths:
        if not pbf_path.exists():
            raise FileNotFoundError(f"OSM PBF not found: {pbf_path}")
        for state_name, boundary in states:
            points = pyogrio.read_dataframe(
                pbf_path,
                layer="points",
                columns=["osm_id", "name", "place", "other_tags"],
                bbox=tuple(float(value) for value in boundary.bounds),
            )
            for _, row in points.iterrows():
                tags = parse_other_tags(row.get("other_tags"))
                place = _safe_text(row.get("place")) or tags.get("place")
                amenity = tags.get("amenity")
                healthcare = tags.get("healthcare")
                railway = tags.get("railway")
                properties = {
                    "name": _safe_text(row.get("name")),
                    "place": place,
                    "amenity": amenity,
                    "healthcare": healthcare,
                    "railway": railway,
                    "source": pbf_path.name,
                }
                if place:
                    _append_record(
                        collected,
                        "settlements_points",
                        _feature_record(row["osm_id"], "points", row.geometry, properties, boundary),
                    )
                if amenity == "school":
                    _append_record(
                        collected,
                        "schools_points",
                        _feature_record(row["osm_id"], "points", row.geometry, properties, boundary),
                    )
                if amenity == "hospital" or healthcare == "hospital":
                    _append_record(
                        collected,
                        "hospitals_points",
                        _feature_record(row["osm_id"], "points", row.geometry, properties, boundary),
                    )
                if railway:
                    _append_record(
                        collected,
                        "railways_points",
                        _feature_record(row["osm_id"], "points", row.geometry, properties, boundary),
                    )
            LOGGER.info("%s / %s: read %d point features", pbf_path.name, state_name, len(points))

    return {
        category: list(collected[category].values())
        for category in POINT_CATEGORIES
    }


def write_exposure_geopackage(
    layers: dict[str, list[dict[str, Any]]],
    output_path: Path,
    force: bool = False,
    append_existing: bool = False,
) -> dict[str, int]:
    if output_path.exists() and not force and not append_existing:
        raise FileExistsError(f"{output_path} exists; pass --force to replace it")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and force:
        output_path.unlink()

    categories = (
        "roads",
        "bridges",
        "settlements",
        "schools",
        "hospitals",
        "railways",
        *POINT_CATEGORIES,
    )
    counts = {}
    for index, category in enumerate(categories):
        if append_existing and category not in POINT_CATEGORIES:
            continue
        records = layers.get(category, [])
        if records:
            frame = gpd.GeoDataFrame(
                [
                    {key: value for key, value in record.items() if key != "geometry"}
                    | {"geometry": record["geometry"]}
                    for record in records
                ],
                geometry="geometry",
                crs="EPSG:4326",
            )
        else:
            frame = gpd.GeoDataFrame(
                columns=[
                    "feature_id",
                    "osm_id",
                    "source_layer",
                    "name",
                    "highway",
                    "bridge",
                    "railway",
                    "amenity",
                    "place",
                    "source",
                    "geometry",
                ],
                geometry="geometry",
                crs="EPSG:4326",
            )
        pyogrio.write_dataframe(
            frame,
            output_path,
            layer=category,
            driver="GPKG",
            append=index > 0 or append_existing,
        )
        counts[category] = len(frame)

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbf", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--points-only",
        action="store_true",
        help="Append point settlements and facilities to an existing GeoPackage.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    state_features, _ = load_grid_boundaries()
    if args.points_only:
        if not args.output.exists():
            raise FileNotFoundError(f"GeoPackage not found: {args.output}")
        existing_layers = {str(row[0]) for row in pyogrio.list_layers(args.output)}
        existing_point_layers = existing_layers.intersection(POINT_CATEGORIES)
        if existing_point_layers:
            raise FileExistsError(
                "Point layers already exist; rebuild the complete GeoPackage with --force"
            )
        layers = collect_exposure_point_layers(args.pbf, state_features)
        counts = write_exposure_geopackage(
            layers, args.output, append_existing=True
        )
    else:
        layers = collect_exposure_layers(args.pbf, state_features)
        counts = write_exposure_geopackage(layers, args.output, force=args.force)
    metadata = {
        "source": "Geofabrik regional OpenStreetMap PBF extracts; OpenStreetMap contributors",
        "source_url": "https://download.geofabrik.de/asia/india.html",
        "license": "Open Data Commons Open Database License 1.0",
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "pbf_files": [
            {
                "name": path.name,
                "downloaded_at": datetime.fromtimestamp(
                    path.stat().st_mtime, timezone.utc
                ).isoformat(),
            }
            for path in args.pbf
        ],
        "target_states": sorted(TARGET_STATE_NAMES),
        "output_crs": "EPSG:4326",
    }
    metadata_path = args.output.with_suffix(".metadata.json")
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "metadata_file": str(metadata_path),
                "counts": counts,
                "metadata": metadata,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()