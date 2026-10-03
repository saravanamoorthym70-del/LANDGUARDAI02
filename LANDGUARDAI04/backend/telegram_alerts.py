import logging
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import requests
from dotenv import load_dotenv

from backend import record_store
from backend.ml_predictor import FEATURES, model


logger = logging.getLogger(__name__)
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
SAFETY_NOTE = (
    "Prototype screening score only, not an official warning. "
    "Follow local authorities' advice."
)
FEATURE_LABELS = {
    "rainfall_1d_mm": ("1-day rainfall", "mm"),
    "rainfall_3d_mm": ("3-day rainfall", "mm"),
    "rainfall_7d_mm": ("7-day rainfall", "mm"),
    "soil_moisture_0_7cm": ("surface soil moisture", "fraction"),
    "elevation_m": ("elevation", "m"),
}


def _environment_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def top_contributing_factors(
    inputs: dict[str, Any], limit: int = 3
) -> list[dict[str, Any]]:
    estimator = model
    if isinstance(estimator, dict) and "model" in estimator:
        estimator = estimator["model"]
    importances = getattr(estimator, "feature_importances_", None)
    if importances is None or len(importances) != len(FEATURES):
        return []

    ranked = sorted(
        zip(FEATURES, importances), key=lambda item: float(item[1]), reverse=True
    )
    factors = []
    for feature_name, importance in ranked[:limit]:
        if feature_name not in inputs:
            continue
        label, unit = FEATURE_LABELS.get(feature_name, (feature_name, ""))
        factors.append(
            {
                "feature": feature_name,
                "label": label,
                "value": inputs[feature_name],
                "unit": unit,
                "global_importance": round(float(importance), 4),
            }
        )
    return factors


def format_alert_message(
    subscription: dict[str, Any], cell: dict[str, Any]
) -> str:
    score = float(cell["risk_score"])
    factors = top_contributing_factors(cell.get("inputs", {}))
    factor_lines = (
        "\n".join(
            f"- {factor['label']}: {factor['value']} {factor['unit']}"
            f" (global model importance {factor['global_importance']:.2f})"
            for factor in factors
        )
        if factors
        else "- Feature importance unavailable for this model artifact"
    )
    return (
        f"LANDGUARD AI screening alert\n"
        f"Location: {subscription['label']}\n"
        f"Band: {cell['risk_band']}\n"
        f"Score: {score:.1f}%\n"
        f"Top model inputs (global importance, not local causes):\n{factor_lines}\n\n"
        f"{SAFETY_NOTE}"
    )


def send_telegram_message(
    chat_id: str,
    text: str,
    token: str | None = None,
    test_mode: bool | None = None,
    test_chat_id: str | None = None,
    post: Callable[..., Any] | None = None,
) -> None:
    token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    if test_mode is None:
        test_mode = _environment_flag("TELEGRAM_TEST_MODE", True)
    test_chat_id = test_chat_id or os.getenv("TELEGRAM_TEST_CHAT_ID")
    if test_mode:
        if not test_chat_id:
            raise RuntimeError(
                "TELEGRAM_TEST_CHAT_ID is required while TELEGRAM_TEST_MODE is enabled"
            )
        chat_id = str(test_chat_id)

    post = post or requests.post
    response = post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": str(chat_id), "text": text},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError("Telegram rejected the message")


def _cell_for_subscription(
    subscription: dict[str, Any]
) -> dict[str, Any] | None:
    if subscription["subscription_type"] == "location":
        return record_store.get_risk_grid_cell_for_location(
            float(subscription["latitude"]), float(subscription["longitude"])
        )
    return record_store.get_risk_grid_cell_for_district(
        subscription["state"], subscription["district"]
    )


def _cooldown_elapsed(
    last_alert_at: str | None, now: datetime, cooldown_hours: float
) -> bool:
    if not last_alert_at:
        return True
    previous_alert = datetime.fromisoformat(last_alert_at.replace("Z", "+00:00"))
    return now - previous_alert >= timedelta(hours=cooldown_hours)


def dispatch_high_risk_alerts(
    token: str | None = None,
    test_mode: bool | None = None,
    test_chat_id: str | None = None,
    cooldown_hours: float | None = None,
    sender: Callable[[str, str], None] | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    if cooldown_hours is None:
        cooldown_hours = float(os.getenv("LANDGUARD_TELEGRAM_COOLDOWN_HOURS", "6"))
    if cooldown_hours < 0:
        raise ValueError("cooldown_hours must not be negative")
    if test_mode is None:
        test_mode = _environment_flag("TELEGRAM_TEST_MODE", True)
    if test_chat_id is None:
        test_chat_id = os.getenv("TELEGRAM_TEST_CHAT_ID")
    if token is None:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if sender is None and token:
        sender = lambda chat_id, text: send_telegram_message(
            chat_id,
            text,
            token=token,
            test_mode=test_mode,
            test_chat_id=test_chat_id,
        )

    counts = {"subscriptions": 0, "sent": 0, "failed": 0, "skipped": 0}
    for subscription in record_store.list_alert_subscriptions():
        counts["subscriptions"] += 1
        cell = _cell_for_subscription(subscription)
        if cell is None:
            counts["skipped"] += 1
            continue

        current_band = str(cell["risk_band"]).upper()
        previous_band = subscription.get("last_band")
        crossed_to_high = previous_band in {"LOW", "MEDIUM"} and current_band == "HIGH"
        within_cooldown = not _cooldown_elapsed(
            subscription.get("last_alert_at"), now, cooldown_hours
        )
        should_send = crossed_to_high and not within_cooldown

        if should_send and test_mode and not test_chat_id:
            logger.warning(
                "Telegram test mode has no TELEGRAM_TEST_CHAT_ID; delivery disabled"
            )
            counts["skipped"] += 1
        elif should_send and sender is None:
            logger.info("Telegram token is not configured; alert delivery disabled")
            counts["skipped"] += 1
        elif should_send:
            recipient = str(test_chat_id) if test_mode else str(subscription["chat_id"])
            try:
                sender(recipient, format_alert_message(subscription, cell))
                counts["sent"] += 1
                record_store.update_alert_subscription_state(
                    subscription["subscription_id"],
                    current_band,
                    now.isoformat(),
                )
                continue
            except Exception as exc:  # Keep the scheduler alive if Telegram is unavailable.
                logger.warning("Telegram alert delivery failed: %s", type(exc).__name__)
                counts["failed"] += 1
                continue
        elif within_cooldown and crossed_to_high:
            counts["skipped"] += 1

        record_store.update_alert_subscription_state(
            subscription["subscription_id"], current_band
        )

    return counts


def _parse_subscription_request(
    chat_id: str, arguments: str
) -> dict[str, Any]:
    parts = arguments.split(maxsplit=3)
    if not parts:
        raise ValueError(
            "Use /subscribe location <latitude> <longitude> [name] or "
            "/subscribe district <district> in <state>."
        )

    subscription_type = parts[0].lower()
    if subscription_type == "location":
        if len(parts) < 3:
            raise ValueError("Use /subscribe location <latitude> <longitude> [name].")
        try:
            latitude = float(parts[1])
            longitude = float(parts[2].split(maxsplit=1)[0])
        except ValueError as exc:
            raise ValueError("Latitude and longitude must be numeric.") from exc
        if not math.isfinite(latitude) or not -90 <= latitude <= 90:
            raise ValueError("Latitude must be between -90 and 90.")
        if not math.isfinite(longitude) or not -180 <= longitude <= 180:
            raise ValueError("Longitude must be between -180 and 180.")
        label_start = arguments.split(maxsplit=3)
        label = label_start[3] if len(label_start) > 3 else f"{latitude:.4f}, {longitude:.4f}"
        return {
            "chat_id": str(chat_id),
            "subscription_type": "location",
            "label": label,
            "latitude": latitude,
            "longitude": longitude,
        }

    if subscription_type == "district":
        district_and_state = arguments[len(parts[0]) :].strip()
        district, separator, state = district_and_state.partition(" in ")
        if not separator or not district.strip() or not state.strip():
            raise ValueError("Use /subscribe district <district> in <state>.")
        district = district.strip()
        state = state.strip()
        return {
            "chat_id": str(chat_id),
            "subscription_type": "district",
            "label": f"{district}, {state}",
            "district": district,
            "state": state,
        }

    raise ValueError("Subscription type must be location or district.")