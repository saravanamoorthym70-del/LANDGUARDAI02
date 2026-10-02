import json

import pytest
import requests
from fastapi.testclient import TestClient
from shapely.geometry import Polygon, shape

from backend import record_store, risk_grid
from backend.main import app
from backend.risk_grid import generate_grid_cells


client = TestClient(app)


def _feature(properties, geometry):
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[list(coordinate) for coordinate in geometry.exterior.coords]],
        },
    }


def test_grid_cells_are_clipped_and_assigned_to_a_district():
    region = Polygon(
        [
            (90.0, 25.0),
            (90.025, 25.0),
            (90.025, 25.025),
            (90.0, 25.025),
            (90.0, 25.0),
        ]
    )
    state = _feature({"name": "Meghalaya", "admin": "India"}, region)
    district = _feature(
        {"shapeName": "Test District", "shapeGroup": "IND", "shapeType": "ADM2"},
        region,
    )

    cells_1000m = list(
        generate_grid_cells([state], [district], 1000, frozenset({"Meghalaya"}))
    )
    cells_500m = list(
        generate_grid_cells([state], [district], 500, frozenset({"Meghalaya"}))
    )

    assert len(cells_1000m) > 1
    assert len(cells_500m) > len(cells_1000m)
    for cell in cells_1000m:
        cell_geometry = shape(cell["geometry"])
        assert cell_geometry.is_valid
        assert region.covers(Polygon(cell_geometry.exterior.coords).representative_point())
        assert cell["state"] == "Meghalaya"
        assert cell["district"] == "Test District"
        assert cell["grid_size_m"] == 1000


def test_grid_rejects_a_missing_target_state():
    try:
        list(generate_grid_cells([], [], target_state_names=frozenset({"Assam"})))
    except ValueError as error:
        assert "Assam" in str(error)
    else:
        raise AssertionError("expected missing target-state validation")


def test_unassigned_center_uses_majority_district_overlap():
    from shapely.geometry import Point, box
    from shapely.strtree import STRtree

    district_geometry = box(0, 0, 6, 10)
    district = {"name": "Majority District", "state": "Meghalaya"}
    matched = risk_grid._match_district(
        Point(8, 5),
        box(0, 0, 10, 10),
        [district],
        [district_geometry],
        STRtree([district_geometry]),
    )

    assert matched == district


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


def _weather_payload(elevation=700):
    return {
        "elevation": elevation,
        "hourly": {
            "time": [f"2026-09-25T{hour % 24:02d}:00" for hour in range(168)],
            "precipitation": [1.0] * 168,
            "soil_moisture_0_to_7cm": [0.3] * 168,
        },
    }


def test_weather_batch_retries_rate_limit_and_parses_each_location(monkeypatch):
    calls = []
    sleeps = []

    def fake_get(url, params, timeout):
        calls.append(params)
        if len(calls) == 1:
            return FakeResponse({}, 429, {"Retry-After": "3"})
        return FakeResponse([_weather_payload(700), _weather_payload(800)])

    monkeypatch.setattr(risk_grid.time, "sleep", sleeps.append)
    cells = [
        {"latitude": 25.5, "longitude": 91.5},
        {"latitude": 26.0, "longitude": 92.0},
    ]

    results = risk_grid._fetch_weather_batch(cells, fake_get)

    assert len(calls) == 2
    assert calls[0]["latitude"] == "25.50000,26.00000"
    assert sleeps == [3.0]
    assert results[0]["rainfall_1d_mm"] == 24.0
    assert results[1]["elevation_m"] == 800.0


def test_grid_job_persists_scores_and_reuses_fresh_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(record_store, "_database_path", lambda: tmp_path / "grid.db")
    record_store.init_db()
    cells = [
        {
            "cell_id": f"1000:0:{column}",
            "grid_size_m": 1000,
            "latitude": 25.5,
            "longitude": 91.5 + column * 0.01,
            "district": "East Khasi Hills",
            "state": "Meghalaya",
            "geometry": {"type": "Polygon", "coordinates": []},
        }
        for column in range(3)
    ]
    calls = []
    monkeypatch.setattr(risk_grid, "load_grid_boundaries", lambda: ([], []))
    monkeypatch.setattr(
        risk_grid, "generate_grid_cells", lambda *args: iter(cells)
    )
    monkeypatch.setattr(risk_grid, "model_is_loaded", lambda: True)
    monkeypatch.setattr(
        risk_grid,
        "predict_risk",
        lambda **kwargs: {"risk_percentage": 82.0, "risk_level": "HIGH"},
    )

    def fake_get(url, params, timeout):
        calls.append(params)
        count = len(params["latitude"].split(","))
        return FakeResponse([_weather_payload() for _ in range(count)])

    first = risk_grid.run_grid_update(
        batch_size=2,
        request_interval_seconds=0,
        request_get=fake_get,
    )
    second = risk_grid.run_grid_update(
        batch_size=2,
        request_interval_seconds=0,
        request_get=fake_get,
    )

    assert first["updated_cells"] == 3
    assert first["complete"] is True
    assert len(calls) == 2
    assert second["cached_cells"] == 3
    assert second["updated_cells"] == 0
    assert len(calls) == 2
    assert record_store.get_risk_grid_district_summary(1000)[0]["high_cells"] == 3


def test_risk_grid_endpoint_returns_geojson_and_validates_bbox(monkeypatch, tmp_path):
    monkeypatch.setattr(record_store, "_database_path", lambda: tmp_path / "api.db")
    record_store.init_db()
    record_store.save_risk_grid_cells(
        [
            {
                "cell_id": "1000:0:0",
                "grid_size_m": 1000,
                "latitude": 25.5,
                "longitude": 91.5,
                "district": "East Khasi Hills",
                "state": "Meghalaya",
                "risk_score": 82.0,
                "risk_band": "HIGH",
                "inputs": {"rainfall_1d_mm": 24.0},
                "geometry": {"type": "Polygon", "coordinates": []},
                "updated_at": "2026-10-02T00:00:00+00:00",
            }
        ]
    )
    record_store.set_risk_grid_metadata(
        {
            "grid_size_m": 1000,
            "complete": True,
            "generated_cells": 1,
            "failed_cells": 0,
        }
    )

    response = client.get(
        "/risk-grid", params={"bbox": "91,25,92,26", "limit": 10}
    )
    invalid = client.get("/risk-grid", params={"bbox": "91,25,92"})

    assert response.status_code == 200
    assert response.json()["type"] == "FeatureCollection"
    assert response.json()["generated_cells"] == 1
    assert response.json()["features"][0]["properties"]["risk_band"] == "HIGH"
    assert response.json()["district_summary"][0]["district"] == "East Khasi Hills"
    assert invalid.status_code == 422