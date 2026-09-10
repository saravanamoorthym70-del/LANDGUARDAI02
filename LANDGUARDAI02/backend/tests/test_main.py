"""
Tests for the LANDGUARD AI FastAPI backend.

Run from the repo root:
    pytest backend/tests -v

External calls (Open-Meteo, Nominatim) are mocked with monkeypatch so
the suite runs offline and deterministically.
"""

import requests
import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


VALID_PAYLOAD = {
    "rainfall_1d_mm": 80,
    "rainfall_3d_mm": 150,
    "rainfall_7d_mm": 300,
    "soil_moisture_0_7cm": 0.45,
    "elevation_m": 1200,
    "slope_deg": 30,
}


# ------------------------------------------------------------------
# Basic endpoints
# ------------------------------------------------------------------

def test_home():
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


# ------------------------------------------------------------------
# /predict-risk
# ------------------------------------------------------------------

def test_predict_risk_high():
    response = client.post("/predict-risk", json=VALID_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["risk_level"] in {"LOW", "MEDIUM", "HIGH"}
    assert 0 <= body["risk_probability"] <= 1
    assert body["risk_percentage"] == pytest.approx(
        body["risk_probability"] * 100, rel=1e-3
    )


def test_predict_risk_low_input_returns_valid_shape():
    """A near-zero-rainfall, flat, low-slope input should still return
    a well-formed result. We don't assert a specific risk_level here —
    that depends on the trained model's learned decision boundary,
    which will shift once the real data pipeline (see ml/scripts)
    replaces the bootstrap dataset."""
    payload = {
        "rainfall_1d_mm": 0,
        "rainfall_3d_mm": 0,
        "rainfall_7d_mm": 2,
        "soil_moisture_0_7cm": 0.1,
        "elevation_m": 50,
        "slope_deg": 1,
    }
    response = client.post("/predict-risk", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["risk_level"] in {"LOW", "MEDIUM", "HIGH"}
    assert 0 <= body["risk_probability"] <= 1


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("rainfall_1d_mm", -1),
        ("soil_moisture_0_7cm", 1.5),
        ("slope_deg", 91),
        ("elevation_m", -1000),
    ],
)
def test_predict_risk_rejects_out_of_range_values(field, bad_value):
    payload = dict(VALID_PAYLOAD)
    payload[field] = bad_value
    response = client.post("/predict-risk", json=payload)
    assert response.status_code == 422


def test_predict_risk_rejects_missing_field():
    payload = dict(VALID_PAYLOAD)
    del payload["slope_deg"]
    response = client.post("/predict-risk", json=payload)
    assert response.status_code == 422


# ------------------------------------------------------------------
# /live-environment — external API mocked
# ------------------------------------------------------------------

class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


def _fake_open_meteo_forecast(*args, **kwargs):
    hours = 24 * 8  # past_days=7 + forecast_days=1
    return FakeResponse(
        {
            "elevation": 900.0,
            "hourly": {
                "time": [f"2026-09-{(i // 24) + 1:02d}T00:00" for i in range(hours)],
                "precipitation": [1.0] * hours,
                "soil_moisture_0_to_7cm": [0.3] * hours,
            },
        }
    )


def test_live_environment_success(monkeypatch):
    monkeypatch.setattr(requests, "get", _fake_open_meteo_forecast)
    response = client.get(
        "/live-environment", params={"latitude": 25.57, "longitude": 91.88}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["rainfall_1d_mm"] == pytest.approx(24.0)
    assert body["rainfall_3d_mm"] == pytest.approx(72.0)
    assert body["rainfall_7d_mm"] == pytest.approx(168.0)
    assert body["elevation_m"] == 900.0


def test_live_environment_upstream_failure(monkeypatch):
    def _raise(*args, **kwargs):
        raise requests.ConnectionError("network down")

    monkeypatch.setattr(requests, "get", _raise)
    response = client.get(
        "/live-environment", params={"latitude": 25.57, "longitude": 91.88}
    )
    assert response.status_code == 502


def test_live_environment_bad_status(monkeypatch):
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: FakeResponse({}, status_code=500)
    )
    response = client.get(
        "/live-environment", params={"latitude": 25.57, "longitude": 91.88}
    )
    assert response.status_code == 502


# ------------------------------------------------------------------
# /live-risk — chains live-environment + elevation grid + prediction
# ------------------------------------------------------------------

def test_live_risk_success(monkeypatch):
    def fake_get(url, *args, **kwargs):
        if "forecast" in url:
            return _fake_open_meteo_forecast()
        if "elevation" in url:
            return FakeResponse({"elevation": [900.0] * 9})
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(requests, "get", fake_get)

    response = client.get(
        "/live-risk", params={"latitude": 25.57, "longitude": 91.88}
    )
    assert response.status_code == 200
    body = response.json()
    assert "prediction" in body
    assert body["prediction"]["risk_level"] in {"LOW", "MEDIUM", "HIGH"}
    assert body["terrain"]["slope_deg"] == pytest.approx(0.0)


def test_live_risk_elevation_service_down(monkeypatch):
    def fake_get(url, *args, **kwargs):
        if "forecast" in url:
            return _fake_open_meteo_forecast()
        raise requests.ConnectionError("elevation service unreachable")

    monkeypatch.setattr(requests, "get", fake_get)

    response = client.get(
        "/live-risk", params={"latitude": 25.57, "longitude": 91.88}
    )
    assert response.status_code == 502


def test_live_risk_malformed_elevation_grid(monkeypatch):
    def fake_get(url, *args, **kwargs):
        if "forecast" in url:
            return _fake_open_meteo_forecast()
        if "elevation" in url:
            return FakeResponse({"elevation": [900.0, 901.0]})  # not 9 values
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(requests, "get", fake_get)

    response = client.get(
        "/live-risk", params={"latitude": 25.57, "longitude": 91.88}
    )
    assert response.status_code == 502


def test_live_risk_missing_elevation_falls_back_to_grid(monkeypatch):
    """environment.elevation_m == None shouldn't crash prediction —
    it should fall back to the elevation grid's centre value."""

    def fake_forecast_no_elevation(*args, **kwargs):
        resp = _fake_open_meteo_forecast()
        resp._json_data = dict(resp._json_data)
        resp._json_data["elevation"] = None
        return resp

    def fake_get(url, *args, **kwargs):
        if "forecast" in url:
            return fake_forecast_no_elevation()
        if "elevation" in url:
            return FakeResponse({"elevation": [850.0] * 9})
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(requests, "get", fake_get)

    response = client.get(
        "/live-risk", params={"latitude": 25.57, "longitude": 91.88}
    )
    assert response.status_code == 200
    assert response.json()["environment"]["elevation_m"] == 850.0


# ------------------------------------------------------------------
# /reverse-geocode
# ------------------------------------------------------------------

def test_reverse_geocode_success(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **k: FakeResponse(
            {
                "display_name": "Shillong, Meghalaya, India",
                "address": {"city": "Shillong", "state": "Meghalaya", "country": "India"},
            }
        ),
    )
    response = client.get(
        "/reverse-geocode", params={"latitude": 25.57, "longitude": 91.88}
    )
    assert response.status_code == 200
    assert response.json()["state"] == "Meghalaya"


def test_reverse_geocode_upstream_failure(monkeypatch):
    def _raise(*args, **kwargs):
        raise requests.Timeout("nominatim timed out")

    monkeypatch.setattr(requests, "get", _raise)
    response = client.get(
        "/reverse-geocode", params={"latitude": 25.57, "longitude": 91.88}
    )
    assert response.status_code == 502


# ------------------------------------------------------------------
# ml_predictor — rule-based fallback when no trained model is loaded
# ------------------------------------------------------------------

def test_predict_risk_fallback_when_model_missing(monkeypatch):
    from backend import ml_predictor

    monkeypatch.setattr(ml_predictor, "model", None)

    result = ml_predictor.predict_risk(
        rainfall_1d_mm=10,
        rainfall_3d_mm=250,
        rainfall_7d_mm=250,
        soil_moisture_0_7cm=0.85,
        elevation_m=1600,
        slope_deg=40,
    )

    assert result["mode"] == "rule_based_fallback"
    assert result["risk_level"] in {"LOW", "MEDIUM", "HIGH"}
    assert 0 <= result["risk_probability"] <= 1


def test_model_is_loaded_reflects_state(monkeypatch):
    from backend import ml_predictor

    monkeypatch.setattr(ml_predictor, "model", None)
    assert ml_predictor.model_is_loaded() is False

    monkeypatch.setattr(ml_predictor, "model", object())
    assert ml_predictor.model_is_loaded() is True


def test_predict_risk_returns_alert_metadata():
    response = client.post("/predict-risk", json=VALID_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["alert_triggered"], bool)
    assert 0 <= body["alert_threshold_percentage"] <= 100
