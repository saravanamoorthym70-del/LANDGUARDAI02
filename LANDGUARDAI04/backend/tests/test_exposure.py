from shapely.geometry import Polygon, mapping
from fastapi.testclient import TestClient
from shapely.geometry import Point, box

from backend import exposure, main
from backend.exposure import EXPOSURE_CATEGORIES, intersect_high_cells
from ml.scripts.build_exposure_data import (
    POINT_CATEGORIES,
    _feature_record,
    write_exposure_geopackage,
)


client = TestClient(main.app)


def _polygon(x1, y1, x2, y2):
    return Polygon([(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)])


def test_exposure_intersections_include_only_features_touching_high_cells():
    cell = {
        "cell_id": "test-cell",
        "latitude": 25.5,
        "longitude": 91.5,
        "district": "East Khasi Hills",
        "state": "Meghalaya",
        "risk_score": 82.0,
        "geometry": mapping(_polygon(0, 0, 1, 1)),
    }
    road = {
        "type": "Feature",
        "id": "lines:1",
        "geometry": mapping(_polygon(0.2, 0.2, 0.8, 0.8)),
        "properties": {"feature_id": "lines:1", "name": "NH 6", "highway": "trunk"},
    }
    outside_road = {
        "type": "Feature",
        "id": "lines:2",
        "geometry": mapping(_polygon(2, 2, 3, 3)),
        "properties": {"feature_id": "lines:2", "name": "Outside road", "highway": "primary"},
    }
    settlement = {
        "type": "Feature",
        "id": "multipolygons:3",
        "geometry": mapping(_polygon(0.4, 0.4, 1.2, 1.2)),
        "properties": {"feature_id": "multipolygons:3", "name": "Test village", "place": "village"},
    }
    layers = {category: [] for category in EXPOSURE_CATEGORIES}
    layers["roads"] = [road, outside_road]
    layers["settlements"] = [settlement]

    result = intersect_high_cells([cell], layers)

    assert result["summary"]["high_cells"] == 1
    assert result["summary"]["roads"] == 1
    assert result["summary"]["settlements"] == 1
    assert result["summary"]["headline"] == (
        "Highway section NH 6 and 1 mapped settlements intersect 1 HIGH cells."
    )
    assert [feature["id"] for feature in result["layers"]["roads"]["features"]] == ["lines:1"]
    assert result["high_cells"][0]["intersections"]["roads"] == ["lines:1"]


def test_point_exposure_feature_is_not_discarded_for_zero_area_geometry():
    feature = _feature_record(
        42,
        "points",
        Point(0.5, 0.5),
        {"name": "Mapped school", "amenity": "school"},
        box(0, 0, 1, 1),
    )

    assert feature is not None
    assert feature["geometry"].geom_type == "Point"
    assert feature["amenity"] == "school"


def test_point_layer_append_preserves_existing_geopackage_layers(tmp_path):
    from shapely.geometry import LineString
    import pyogrio

    output_path = tmp_path / "exposure.gpkg"
    empty_layers = {category: [] for category in (*EXPOSURE_CATEGORIES, *POINT_CATEGORIES)}
    empty_layers["roads"] = [
        {
            "feature_id": "lines:1",
            "osm_id": "1",
            "source_layer": "lines",
            "name": "Test road",
            "highway": "trunk",
            "bridge": None,
            "railway": None,
            "amenity": None,
            "place": None,
            "source": "test.pbf",
            "geometry": LineString([(0, 0), (1, 1)]),
        }
    ]
    write_exposure_geopackage(empty_layers, output_path)

    points = {category: [] for category in (*EXPOSURE_CATEGORIES, *POINT_CATEGORIES)}
    points["schools_points"] = [
        {
            "feature_id": "points:2",
            "osm_id": "2",
            "source_layer": "points",
            "name": "Test school",
            "highway": None,
            "bridge": None,
            "railway": None,
            "amenity": "school",
            "place": None,
            "source": "test.pbf",
            "geometry": Point(0.5, 0.5),
        }
    ]
    write_exposure_geopackage(points, output_path, append_existing=True)

    layers = {str(row[0]) for row in pyogrio.list_layers(output_path)}
    assert "roads" in layers
    assert "schools_points" in layers
    assert pyogrio.read_dataframe(output_path, layer="roads").shape[0] == 1
    assert pyogrio.read_dataframe(output_path, layer="schools_points").shape[0] == 1


def test_exposure_intersection_returns_all_empty_layers_without_high_cells():
    result = intersect_high_cells([], {category: [] for category in EXPOSURE_CATEGORIES})

    assert result["summary"]["high_cells"] == 0
    assert set(result["layers"]) == set(EXPOSURE_CATEGORIES)
    assert all(not layer["features"] for layer in result["layers"].values())


def test_exposure_endpoint_validates_bbox_and_returns_layer_contract(monkeypatch):
    expected = {
        "summary": {"high_cells": 0},
        "layers": {category: {"type": "FeatureCollection", "features": []} for category in EXPOSURE_CATEGORIES},
        "high_cells": [],
    }
    monkeypatch.setattr(main, "get_exposure_geojson", lambda bbox, limit: expected)

    response = client.get("/exposure", params={"bbox": "91,25,92,26", "limit": 10})
    invalid = client.get("/exposure", params={"bbox": "91,25,92"})

    assert response.status_code == 200
    assert response.json() == expected
    assert invalid.status_code == 422


def test_exposure_skips_osm_read_when_no_high_cells():
    result = exposure.get_exposure_geojson(
        (91.0, 25.0, 92.0, 26.0),
        layer_reader=lambda *_args: (_ for _ in ()).throw(
            AssertionError("layer reader should not be called without HIGH cells")
        ),
        high_cell_reader=lambda *_args: [],
    )

    assert result["summary"]["high_cells"] == 0
    assert all(not layer["features"] for layer in result["layers"].values())