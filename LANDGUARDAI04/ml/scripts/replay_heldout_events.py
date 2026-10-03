"""Replay the saved model on positive rows in its chronological holdout."""

import json
import os
import time
from datetime import date, datetime
from typing import Any

import pandas as pd
import requests

from backend.replay import fetch_historical_weather, score_daily_replay
from ml.scripts.common import DATASET_DIR


DATA_PATH = os.path.join(DATASET_DIR, "LANDGUARD_FINAL_DATASET.csv")
MODEL_METRICS_PATH = os.path.join(
    os.path.dirname(DATASET_DIR), "models", "model_metrics.json"
)


def select_heldout_positive_events(
    data: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Timestamp]:
    date_values = pd.Series(pd.NaT, index=data.index, dtype="datetime64[ns]")
    for column in ("event_date", "sample_date"):
        if column in data:
            date_values = date_values.fillna(
                pd.to_datetime(data[column], errors="coerce")
            )
    valid_dates = date_values.notna()
    if valid_dates.sum() < 10:
        raise ValueError("Not enough dated dataset rows for the training holdout")
    cutoff = date_values.loc[valid_dates].quantile(0.8)
    test_mask = valid_dates & (date_values > cutoff)
    positives = data.loc[test_mask & data["risk"].eq(1)].copy()
    positives["_parsed_event_date"] = pd.to_datetime(
        positives["event_date"], errors="coerce"
    )
    return positives.loc[positives["_parsed_event_date"].notna()], cutoff


def run_heldout_replay(
    days: int = 7,
    request_get: Any = None,
    sleep: Any = time.sleep,
    request_interval_seconds: float = 1.0,
) -> dict[str, Any]:
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Missing training dataset: {DATA_PATH}")
    data = pd.read_csv(DATA_PATH)
    heldout_events, cutoff = select_heldout_positive_events(data)
    report = {
        "method": "same chronological 80/20 date split as model training",
        "cutoff": cutoff.isoformat(),
        "selected_model": json.load(open(MODEL_METRICS_PATH, encoding="utf-8"))[
            "temporal_validation"
        ]["selected_model"],
        "replay_days": days,
        "heldout_positive_events": int(len(heldout_events)),
        "attempted_events": 0,
        "successful_events": 0,
        "reached_high_events": 0,
        "false_alarm_non_event_days": 0,
        "locations_with_false_alarm": 0,
        "lead_time_days": [],
        "failures": [],
        "score_semantics": "prototype screening score; not a calibrated event probability",
    }
    request_get = request_get or requests.get
    last_request_at = 0.0

    for _, row in heldout_events.iterrows():
        report["attempted_events"] += 1
        event_date = row["_parsed_event_date"].date()
        try:
            elapsed = time.monotonic() - last_request_at
            if last_request_at and elapsed < request_interval_seconds:
                sleep(request_interval_seconds - elapsed)
            weather = fetch_historical_weather(
                float(row["latitude"]),
                float(row["longitude"]),
                event_date,
                days=days,
                request_get=request_get,
            )
            last_request_at = time.monotonic()
            daily_scores = score_daily_replay(
                float(row["latitude"]),
                float(row["longitude"]),
                event_date,
                weather.get("hourly", {}),
                float(row["elevation_m"]),
                days=days,
            )
            report["successful_events"] += 1
            high_days = [
                score
                for score in daily_scores
                if score["risk_band"] == "HIGH"
            ]
            report["false_alarm_non_event_days"] += len(high_days)
            if high_days:
                report["reached_high_events"] += 1
                report["locations_with_false_alarm"] += 1
                first_high_date = min(date.fromisoformat(score["date"]) for score in high_days)
                report["lead_time_days"].append((event_date - first_high_date).days)
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            report["failures"].append(
                {
                    "event_id": str(row.get("event_id", "")),
                    "event_date": event_date.isoformat(),
                    "error": type(exc).__name__,
                }
            )

    lead_times = report["lead_time_days"]
    report["lead_time_summary"] = {
        "events_with_high_before_event": len(lead_times),
        "mean_days": round(sum(lead_times) / len(lead_times), 2) if lead_times else None,
        "median_days": float(pd.Series(lead_times).median()) if lead_times else None,
    }
    report["false_alarm_note"] = (
        "HIGH-score replay days in each held-out event's pre-event window are counted "
        "as non-event-day false alarms; the dataset does not provide independently "
        "verified negative days at these locations."
    )
    return report


def main() -> None:
    report = run_heldout_replay(
        days=int(os.getenv("LANDGUARD_REPLAY_DAYS", "7")),
        request_interval_seconds=float(
            os.getenv("LANDGUARD_REPLAY_REQUEST_INTERVAL_SECONDS", "1")
        ),
    )
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()