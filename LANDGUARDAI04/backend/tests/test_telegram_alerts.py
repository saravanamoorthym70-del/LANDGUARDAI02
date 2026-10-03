from datetime import datetime, timedelta, timezone

from backend import record_store
from backend.telegram_alerts import dispatch_high_risk_alerts, send_telegram_message
from backend.telegram_bot import handle_update


def _grid_cell(risk_band, risk_score):
    return {
        "cell_id": "1000:0:0",
        "grid_size_m": 1000,
        "latitude": 25.57,
        "longitude": 91.88,
        "district": "East Khasi Hills",
        "state": "Meghalaya",
        "risk_score": risk_score,
        "risk_band": risk_band,
        "inputs": {
            "rainfall_1d_mm": 120.0,
            "rainfall_3d_mm": 210.0,
            "rainfall_7d_mm": 340.0,
            "soil_moisture_0_7cm": 0.7,
            "elevation_m": 1100.0,
        },
        "geometry": {"type": "Polygon", "coordinates": []},
        "updated_at": "2026-10-02T00:00:00+00:00",
    }


def test_alert_sends_only_on_high_transition_and_obeys_cooldown(monkeypatch, tmp_path):
    monkeypatch.setattr(record_store, "_database_path", lambda: tmp_path / "alerts.db")
    record_store.init_db()
    subscription = record_store.create_alert_subscription(
        {
            "chat_id": "12345",
            "subscription_type": "district",
            "label": "East Khasi Hills, Meghalaya",
            "district": "East Khasi Hills",
            "state": "Meghalaya",
        }
    )
    duplicate = record_store.create_alert_subscription(
        {
            "chat_id": "12345",
            "subscription_type": "district",
            "label": "East Khasi Hills, Meghalaya",
            "district": "East Khasi Hills",
            "state": "Meghalaya",
        }
    )
    assert duplicate["subscription_id"] == subscription["subscription_id"]

    sent = []
    start = datetime(2026, 10, 2, tzinfo=timezone.utc)
    record_store.set_risk_grid_metadata({"grid_size_m": 1000, "complete": True})
    record_store.save_risk_grid_cells([_grid_cell("LOW", 20.0)])
    first = dispatch_high_risk_alerts(
        token="test-token",
        test_mode=True,
        test_chat_id="own-chat",
        sender=lambda chat_id, text: sent.append((chat_id, text)),
        now=start,
    )
    assert first["sent"] == 0
    assert not sent

    record_store.save_risk_grid_cells([_grid_cell("HIGH", 82.0)])
    second = dispatch_high_risk_alerts(
        token="test-token",
        test_mode=True,
        test_chat_id="own-chat",
        sender=lambda chat_id, text: sent.append((chat_id, text)),
        now=start + timedelta(hours=1),
    )
    repeated = dispatch_high_risk_alerts(
        token="test-token",
        test_mode=True,
        test_chat_id="own-chat",
        sender=lambda chat_id, text: sent.append((chat_id, text)),
        now=start + timedelta(hours=2),
    )
    assert second["sent"] == 1
    assert repeated["sent"] == 0
    assert sent[0][0] == "own-chat"
    assert "82.0%" in sent[0][1]
    assert "Prototype screening score only, not an official warning" in sent[0][1]
    assert "global importance" in sent[0][1]

    record_store.save_risk_grid_cells([_grid_cell("LOW", 30.0)])
    dispatch_high_risk_alerts(
        token="test-token",
        test_mode=True,
        test_chat_id="own-chat",
        sender=lambda chat_id, text: sent.append((chat_id, text)),
        now=start + timedelta(hours=3),
    )
    record_store.save_risk_grid_cells([_grid_cell("HIGH", 85.0)])
    cooldown = dispatch_high_risk_alerts(
        token="test-token",
        test_mode=True,
        test_chat_id="own-chat",
        sender=lambda chat_id, text: sent.append((chat_id, text)),
        now=start + timedelta(hours=4),
    )
    assert cooldown["sent"] == 0
    assert cooldown["skipped"] == 1
    assert len(sent) == 1

    record_store.save_risk_grid_cells([_grid_cell("LOW", 30.0)])
    dispatch_high_risk_alerts(
        token="test-token",
        test_mode=True,
        test_chat_id="own-chat",
        sender=lambda chat_id, text: sent.append((chat_id, text)),
        now=start + timedelta(hours=8),
    )
    record_store.save_risk_grid_cells([_grid_cell("HIGH", 85.0)])
    after_cooldown = dispatch_high_risk_alerts(
        token="test-token",
        test_mode=True,
        test_chat_id="own-chat",
        sender=lambda chat_id, text: sent.append((chat_id, text)),
        now=start + timedelta(hours=9),
    )
    assert after_cooldown["sent"] == 1
    assert len(sent) == 2


def test_bot_commands_are_restricted_to_test_chat_and_unsubscribe_is_owner_scoped(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(record_store, "_database_path", lambda: tmp_path / "bot.db")
    record_store.init_db()
    responses = []
    update = {
        "message": {
            "chat": {"id": 100},
            "text": "/subscribe location 25.57 91.88 Shillong",
        }
    }

    handle_update(
        update,
        lambda chat_id, text: responses.append((chat_id, text)),
        test_mode=True,
        test_chat_id="999",
    )
    assert record_store.list_alert_subscriptions() == []

    update["message"]["chat"]["id"] = 999
    handle_update(
        update,
        lambda chat_id, text: responses.append((chat_id, text)),
        test_mode=True,
        test_chat_id="999",
    )
    subscriptions = record_store.list_alert_subscriptions()
    assert len(subscriptions) == 1
    assert subscriptions[0]["label"] == "Shillong"

    removed = record_store.delete_alert_subscription(
        subscriptions[0]["subscription_id"], "100"
    )
    assert removed is False
    handle_update(
        {
            "message": {
                "chat": {"id": 999},
                "text": f"/unsubscribe {subscriptions[0]['subscription_id']}",
            }
        },
        lambda chat_id, text: responses.append((chat_id, text)),
        test_mode=True,
        test_chat_id="999",
    )
    assert record_store.list_alert_subscriptions() == []


def test_start_reveals_test_chat_id_when_bootstrapping():
    responses = []
    handle_update(
        {"message": {"chat": {"id": 999}, "text": "/start"}},
        lambda chat_id, text: responses.append((chat_id, text)),
        test_mode=True,
        test_chat_id=None,
    )

    assert responses[0][0] == "999"
    assert "Your chat ID is 999" in responses[0][1]


def test_telegram_send_test_mode_overrides_recipient():
    calls = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    def fake_post(url, json, timeout):
        calls.append((url, json, timeout))
        return Response()

    send_telegram_message(
        "not-the-test-chat",
        "prototype test",
        token="redacted-token",
        test_mode=True,
        test_chat_id="my-chat",
        post=fake_post,
    )

    assert calls[0][1]["chat_id"] == "my-chat"


def test_failed_telegram_send_does_not_acknowledge_high_transition(monkeypatch, tmp_path):
    monkeypatch.setattr(record_store, "_database_path", lambda: tmp_path / "retry.db")
    record_store.init_db()
    record_store.create_alert_subscription(
        {
            "chat_id": "12345",
            "subscription_type": "district",
            "label": "East Khasi Hills, Meghalaya",
            "district": "East Khasi Hills",
            "state": "Meghalaya",
        }
    )
    record_store.set_risk_grid_metadata({"grid_size_m": 1000, "complete": True})
    record_store.save_risk_grid_cells([_grid_cell("LOW", 20.0)])
    dispatch_high_risk_alerts(
        token="test-token",
        test_mode=True,
        test_chat_id="own-chat",
        sender=lambda _chat, _text: None,
    )
    record_store.save_risk_grid_cells([_grid_cell("HIGH", 82.0)])

    failed = dispatch_high_risk_alerts(
        token="test-token",
        test_mode=True,
        test_chat_id="own-chat",
        sender=lambda _chat, _text: (_ for _ in ()).throw(RuntimeError("network")),
    )
    saved = record_store.list_alert_subscriptions()[0]
    sent = []
    retried = dispatch_high_risk_alerts(
        token="test-token",
        test_mode=True,
        test_chat_id="own-chat",
        sender=lambda chat, text: sent.append((chat, text)),
    )

    assert failed["failed"] == 1
    assert saved["last_band"] == "LOW"
    assert retried["sent"] == 1
    assert len(sent) == 1