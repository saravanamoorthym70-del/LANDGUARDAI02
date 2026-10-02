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
from backend import record_store

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


def test_historical_events_endpoint_reads_catalog(monkeypatch, tmp_path):
    from backend import main

    catalog = tmp_path / "events.csv"
    catalog.write_text(
        "event_id,event_date,event_title,location,latitude,longitude,state,landslide_category,landslide_trigger,landslide_size\n"
        "42,2024-06-01,Test slide,Test ridge,25.5,91.5,Meghalaya,landslide,rain,small\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(main, "HISTORICAL_EVENTS_CSV", str(catalog))

    response = client.get("/historical-events")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["events"][0]["event_id"] == "42"
    assert body["events"][0]["latitude"] == 25.5
    assert body["events"][0]["trigger"] == "rain"
    assert "risk_level" not in body["events"][0]


def test_live_records_crud(monkeypatch, tmp_path):
    monkeypatch.setattr(record_store, "_database_path", lambda: tmp_path / "records.db")
    record_store.init_db()

    payload = {
        "location_name": "Shillong, Meghalaya",
        "latitude": 25.57,
        "longitude": 91.88,
        "risk_level": "MEDIUM",
        "risk_percentage": 42.5,
        "rainfall_1d_mm": 32.1,
        "rainfall_3d_mm": 88.4,
        "rainfall_7d_mm": 145.0,
        "soil_moisture_0_7cm": 0.42,
        "elevation_m": 1496,
        "slope_deg": 18.2,
        "session_id": "browser-session-1",
        "correlation_id": "assessment-1",
        "trigger": "map-click",
        "captured_at": "2026-09-15T07:00:00+00:00",
        "raw_result": {"prediction": {"risk_level": "MEDIUM"}},
    }

    created = client.post("/records", json=payload)
    assert created.status_code == 201
    assert created.json()["id"]
    assert created.json()["session_id"] == "browser-session-1"
    assert created.json()["correlation_id"] == "assessment-1"
    assert created.json()["trigger"] == "map-click"
    assert created.json()["client_captured_at"] == "2026-09-15T07:00:00+00:00"
    assert created.json()["captured_at"] != payload["captured_at"]
    assert created.json()["raw_result"] == payload["raw_result"]

    listed = client.get("/records")
    assert listed.status_code == 200
    assert len(listed.json()["records"]) == 1
    assert listed.json()["records"][0]["location_name"] == "Shillong, Meghalaya"

    fetched = client.get(f"/records/{created.json()['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["correlation_id"] == "assessment-1"

    missing = client.get("/records/missing-record")
    assert missing.status_code == 404

    cleared = client.delete("/records")
    assert cleared.status_code == 200
    assert client.get("/records").json()["records"] == []


def test_live_records_reject_invalid_coordinates():
    response = client.post(
        "/records",
        json={"latitude": 95, "longitude": 91, "risk_level": "HIGH"},
    )
    assert response.status_code == 422


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
        self.text = str(json_data)

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


def test_live_environment_uses_nasa_power_when_open_meteo_is_rate_limited(monkeypatch):
    daily_rainfall = {
        "20260923": 1,
        "20260924": 2,
        "20260925": 3,
        "20260926": 4,
        "20260927": 5,
        "20260928": 6,
        "20260929": 7,
    }
    daily_soil_moisture = {day: 0.6 for day in daily_rainfall}

    def fake_get(url, *args, **kwargs):
        if "forecast" in url:
            return FakeResponse({}, status_code=429)
        if "power.larc.nasa.gov" in url:
            return FakeResponse(
                {
                    "properties": {
                        "parameter": {
                            "PRECTOTCORR": daily_rainfall,
                            "GWETTOP": daily_soil_moisture,
                        }
                    }
                }
            )
        if "elevation" in url:
            return FakeResponse({"elevation": [540.0] * 9})
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(requests, "get", fake_get)

    response = client.get(
        "/live-environment", params={"latitude": 25.57, "longitude": 91.88}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data_source"] == "NASA POWER"
    assert body["observed_through"] == "2026-09-29"
    assert body["is_live_data"] is False
    assert body["rainfall_1d_mm"] == 7
    assert body["rainfall_3d_mm"] == 18
    assert body["rainfall_7d_mm"] == 28
    assert body["soil_moisture_0_7cm"] == 0.6

    risk_response = client.get(
        "/live-risk", params={"latitude": 25.57, "longitude": 91.88}
    )
    assert risk_response.status_code == 200
    assert risk_response.json()["environment"]["data_source"] == "NASA POWER"
    assert risk_response.json()["prediction"]["risk_level"] in {"LOW", "MEDIUM", "HIGH"}


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


def test_legacy_alert_threshold_cannot_trigger_below_high_band(monkeypatch):
    from backend import ml_predictor

    class FixedProbabilityModel:
        def predict_proba(self, _features):
            return [[0.35, 0.65]]

    monkeypatch.setattr(
        ml_predictor,
        "model",
        {"model": FixedProbabilityModel(), "warning_threshold": 0.3227},
    )
    result = ml_predictor.predict_risk(
        rainfall_1d_mm=0.8,
        rainfall_3d_mm=1.1,
        rainfall_7d_mm=1.6,
        soil_moisture_0_7cm=0.277,
        elevation_m=328,
        slope_deg=1.67,
    )

    assert result["risk_level"] == "MEDIUM"
    assert result["alert_triggered"] is False
    assert result["alert_threshold_percentage"] == 70.0
    assert "not a calibrated event probability" in result["score_semantics"]
