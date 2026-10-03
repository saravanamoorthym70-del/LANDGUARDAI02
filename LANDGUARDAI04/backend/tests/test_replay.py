from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from backend import main, replay


client = TestClient(main.app)


class FakeResponse:
    status_code = 200
    headers = {}

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


def test_fetch_history_uses_archive_source_and_excludes_event_date(monkeypatch):
    event_date = date(2026, 10, 2)
    captured = []

    def fake_get(url, params, timeout):
        captured.append((url, params))
        start = date.fromisoformat(params["start_date"])
        end = date.fromisoformat(params["end_date"])
        times = []
        current = datetime.combine(start, datetime.min.time())
        last = datetime.combine(end, datetime.max.time()).replace(minute=0, second=0, microsecond=0)
        while current <= last:
            times.append(current.isoformat(timespec="minutes"))
            current += timedelta(hours=1)
        return FakeResponse(
            {
                "elevation": 1200,
                "hourly": {
                    "time": times,
                    "precipitation": [1.0] * len(times),
                    "soil_moisture_0_to_7cm": [0.4] * len(times),
                },
            }
        )

    payload = replay.fetch_historical_weather(
        25.5, 91.5, event_date, days=7, request_get=fake_get
    )
    observed = []

    def scorer(**features):
        observed.append(features)
        return {"risk_percentage": 75.0, "risk_level": "HIGH", "risk_probability": 0.75}

    scores = replay.score_daily_replay(
        25.5,
        91.5,
        event_date,
        payload["hourly"],
        payload["elevation"],
        days=7,
        scorer=scorer,
    )

    assert captured[0][0] == replay.OPEN_METEO_ARCHIVE_URL
    assert captured[0][1]["start_date"] == "2026-09-19"
    assert captured[0][1]["end_date"] == "2026-10-01"
    assert "models" not in captured[0][1]
    assert len(scores) == 7
    assert scores[0]["date"] == "2026-09-25"
    assert scores[-1]["date"] == "2026-10-01"
    assert all(score["risk_band"] == "HIGH" for score in scores)
    assert observed[0]["rainfall_1d_mm"] == 24.0
    assert observed[0]["rainfall_3d_mm"] == 72.0
    assert observed[0]["rainfall_7d_mm"] == 168.0
    assert observed[0]["elevation_m"] == 1200.0


def test_replay_endpoint_returns_daily_scores(monkeypatch):
    expected = {
        "event_date": "2026-10-02",
        "daily_scores": [{"date": "2026-10-01", "risk_score": 10.0, "risk_band": "LOW"}],
    }
    monkeypatch.setattr(main, "replay_location", lambda *args, **kwargs: expected)

    response = client.get(
        "/replay",
        params={"latitude": 25.5, "longitude": 91.5, "date": "2026-10-02", "days": 1},
    )
    invalid = client.get(
        "/replay",
        params={"latitude": 25.5, "longitude": 91.5, "date": "2026-10-02", "days": 31},
    )

    assert response.status_code == 200
    assert response.json() == expected
    assert invalid.status_code == 422