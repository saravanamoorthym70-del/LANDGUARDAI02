import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "landguard.db"


def _database_path() -> Path:
    return Path(os.environ.get("LANDGUARD_DB_PATH", str(DEFAULT_DB_PATH)))


def _connect() -> sqlite3.Connection:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS live_records (
                id TEXT PRIMARY KEY,
                captured_at TEXT NOT NULL,
                client_captured_at TEXT,
                session_id TEXT,
                correlation_id TEXT NOT NULL,
                trigger TEXT NOT NULL,
                location_name TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                risk_level TEXT NOT NULL,
                risk_percentage REAL,
                rainfall_1d_mm REAL,
                rainfall_3d_mm REAL,
                rainfall_7d_mm REAL,
                soil_moisture_0_7cm REAL,
                elevation_m REAL,
                slope_deg REAL,
                raw_result TEXT NOT NULL
            )
            """
        )
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(live_records)")
        }
        migrations = {
            "client_captured_at": "ALTER TABLE live_records ADD COLUMN client_captured_at TEXT",
            "session_id": "ALTER TABLE live_records ADD COLUMN session_id TEXT",
            "correlation_id": "ALTER TABLE live_records ADD COLUMN correlation_id TEXT",
            "trigger": "ALTER TABLE live_records ADD COLUMN trigger TEXT",
        }
        for column, statement in migrations.items():
            if column not in columns:
                connection.execute(statement)

        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_live_records_correlation_id "
            "ON live_records (correlation_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_live_records_captured_at "
            "ON live_records (captured_at DESC)"
        )


def create_record(record: dict[str, Any]) -> dict[str, Any]:
    record_id = str(uuid.uuid4())
    captured_at = datetime.now(timezone.utc).isoformat()
    stored = {
        "id": record_id,
        **record,
        "captured_at": captured_at,
        "correlation_id": record.get("correlation_id") or str(uuid.uuid4()),
        "trigger": record.get("trigger") or "map-click",
    }

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO live_records (
                id, captured_at, client_captured_at, session_id, correlation_id,
                trigger, location_name, latitude, longitude,
                risk_level, risk_percentage, rainfall_1d_mm, rainfall_3d_mm,
                rainfall_7d_mm, soil_moisture_0_7cm, elevation_m, slope_deg,
                raw_result
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                captured_at,
                stored.get("client_captured_at"),
                stored.get("session_id"),
                stored["correlation_id"],
                stored["trigger"],
                stored.get("location_name", "Selected map location"),
                stored["latitude"],
                stored["longitude"],
                stored["risk_level"],
                stored.get("risk_percentage"),
                stored.get("rainfall_1d_mm"),
                stored.get("rainfall_3d_mm"),
                stored.get("rainfall_7d_mm"),
                stored.get("soil_moisture_0_7cm"),
                stored.get("elevation_m"),
                stored.get("slope_deg"),
                json.dumps(stored.get("raw_result", {})),
            ),
        )
    return stored


def list_records(limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = min(max(int(limit), 1), 200)
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM live_records ORDER BY captured_at DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()

    records = []
    for row in rows:
        record = dict(row)
        record["raw_result"] = json.loads(record["raw_result"])
        records.append(record)
    return records


def get_record(record_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM live_records WHERE id = ?",
            (record_id,),
        ).fetchone()

    if row is None:
        return None

    record = dict(row)
    record["raw_result"] = json.loads(record["raw_result"])
    return record


def delete_all_records() -> None:
    with _connect() as connection:
        connection.execute("DELETE FROM live_records")
