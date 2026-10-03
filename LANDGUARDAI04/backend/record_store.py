import json
import math
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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS risk_grid_cells (
                cell_id TEXT PRIMARY KEY,
                grid_size_m INTEGER NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                district TEXT,
                state TEXT,
                risk_score REAL NOT NULL,
                risk_band TEXT NOT NULL,
                inputs_json TEXT NOT NULL,
                geometry_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_risk_grid_bbox "
            "ON risk_grid_cells (grid_size_m, longitude, latitude)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_risk_grid_district "
            "ON risk_grid_cells (grid_size_m, state, district, risk_score DESC)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS risk_grid_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS alert_subscriptions (
                subscription_id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                subscription_type TEXT NOT NULL,
                label TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                state TEXT,
                district TEXT,
                last_band TEXT,
                last_alert_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_alert_subscriptions_chat "
            "ON alert_subscriptions (chat_id, created_at)"
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


def get_fresh_risk_grid_cell_ids(
    cell_ids: list[str], grid_size_m: int, fresh_after: str
) -> set[str]:
    fresh_ids: set[str] = set()
    with _connect() as connection:
        for offset in range(0, len(cell_ids), 500):
            batch = cell_ids[offset : offset + 500]
            if not batch:
                continue
            placeholders = ",".join("?" for _ in batch)
            rows = connection.execute(
                f"SELECT cell_id FROM risk_grid_cells "
                f"WHERE grid_size_m = ? AND updated_at >= ? "
                f"AND cell_id IN ({placeholders})",
                (grid_size_m, fresh_after, *batch),
            ).fetchall()
            fresh_ids.update(row["cell_id"] for row in rows)
    return fresh_ids


def save_risk_grid_cells(cells: list[dict[str, Any]]) -> None:
    if not cells:
        return
    with _connect() as connection:
        connection.executemany(
            """
            INSERT INTO risk_grid_cells (
                cell_id, grid_size_m, latitude, longitude, district, state,
                risk_score, risk_band, inputs_json, geometry_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cell_id) DO UPDATE SET
                grid_size_m = excluded.grid_size_m,
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                district = excluded.district,
                state = excluded.state,
                risk_score = excluded.risk_score,
                risk_band = excluded.risk_band,
                inputs_json = excluded.inputs_json,
                geometry_json = excluded.geometry_json,
                updated_at = excluded.updated_at
            """,
            [
                (
                    cell["cell_id"],
                    cell["grid_size_m"],
                    cell["latitude"],
                    cell["longitude"],
                    cell.get("district"),
                    cell.get("state"),
                    cell["risk_score"],
                    cell["risk_band"],
                    json.dumps(cell["inputs"], allow_nan=False),
                    json.dumps(cell["geometry"], allow_nan=False),
                    cell["updated_at"],
                )
                for cell in cells
            ],
        )


def set_risk_grid_metadata(metadata: dict[str, Any]) -> None:
    with _connect() as connection:
        connection.execute(
            "INSERT INTO risk_grid_metadata (key, value) VALUES ('active', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(metadata, allow_nan=False),),
        )


def get_risk_grid_metadata() -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT value FROM risk_grid_metadata WHERE key = 'active'"
        ).fetchone()
    return json.loads(row["value"]) if row else None


def get_risk_grid_cells(
    grid_size_m: int,
    bbox: tuple[float, float, float, float] | None,
    limit: int,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM risk_grid_cells WHERE grid_size_m = ?"
    parameters: list[Any] = [grid_size_m]
    if bbox is not None:
        min_lon, min_lat, max_lon, max_lat = bbox
        query += " AND longitude BETWEEN ? AND ? AND latitude BETWEEN ? AND ?"
        parameters.extend((min_lon, max_lon, min_lat, max_lat))
    query += " ORDER BY risk_score DESC, updated_at DESC LIMIT ?"
    parameters.append(limit)

    with _connect() as connection:
        rows = connection.execute(query, parameters).fetchall()

    cells = []
    for row in rows:
        cell = dict(row)
        cell["inputs"] = json.loads(cell.pop("inputs_json"))
        cell["geometry"] = json.loads(cell.pop("geometry_json"))
        cells.append(cell)
    return cells


def get_risk_grid_district_summary(
    grid_size_m: int, limit: int = 10
) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT district, state, COUNT(*) AS cell_count,
                SUM(CASE WHEN risk_band = 'HIGH' THEN 1 ELSE 0 END) AS high_cells,
                MAX(risk_score) AS max_score,
                AVG(risk_score) AS mean_score,
                MAX(updated_at) AS updated_at
            FROM risk_grid_cells
            WHERE grid_size_m = ? AND district IS NOT NULL
            GROUP BY state, district
            ORDER BY max_score DESC, high_cells DESC, mean_score DESC, district
            LIMIT ?
            """,
            (grid_size_m, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def get_risk_grid_last_updated(grid_size_m: int) -> str | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT MAX(updated_at) AS updated_at FROM risk_grid_cells "
            "WHERE grid_size_m = ?",
            (grid_size_m,),
        ).fetchone()
    return row["updated_at"] if row else None


def create_alert_subscription(subscription: dict[str, Any]) -> dict[str, Any]:
    subscription_type = subscription["subscription_type"]
    if subscription_type == "location":
        duplicate_query = (
            "SELECT * FROM alert_subscriptions WHERE chat_id = ? "
            "AND subscription_type = 'location' AND latitude = ? AND longitude = ?"
        )
        duplicate_values = (
            subscription["chat_id"],
            subscription["latitude"],
            subscription["longitude"],
        )
    elif subscription_type == "district":
        duplicate_query = (
            "SELECT * FROM alert_subscriptions WHERE chat_id = ? "
            "AND subscription_type = 'district' AND lower(state) = lower(?) "
            "AND lower(district) = lower(?)"
        )
        duplicate_values = (
            subscription["chat_id"],
            subscription["state"],
            subscription["district"],
        )
    else:
        raise ValueError("subscription_type must be location or district")

    with _connect() as connection:
        existing = connection.execute(duplicate_query, duplicate_values).fetchone()
        if existing:
            return dict(existing)

        stored = {
            "subscription_id": str(uuid.uuid4()),
            **subscription,
            "last_band": None,
            "last_alert_at": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        connection.execute(
            """
            INSERT INTO alert_subscriptions (
                subscription_id, chat_id, subscription_type, label, latitude,
                longitude, state, district, last_band, last_alert_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(
                stored.get(key)
                for key in (
                    "subscription_id",
                    "chat_id",
                    "subscription_type",
                    "label",
                    "latitude",
                    "longitude",
                    "state",
                    "district",
                    "last_band",
                    "last_alert_at",
                    "created_at",
                )
            ),
        )
    return stored


def list_alert_subscriptions(chat_id: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM alert_subscriptions"
    parameters: tuple[Any, ...] = ()
    if chat_id is not None:
        query += " WHERE chat_id = ?"
        parameters = (str(chat_id),)
    query += " ORDER BY created_at, subscription_id"
    with _connect() as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


def delete_alert_subscription(subscription_id: str, chat_id: str) -> bool:
    with _connect() as connection:
        cursor = connection.execute(
            "DELETE FROM alert_subscriptions WHERE subscription_id = ? AND chat_id = ?",
            (subscription_id, str(chat_id)),
        )
    return cursor.rowcount > 0


def update_alert_subscription_state(
    subscription_id: str,
    risk_band: str,
    last_alert_at: str | None = None,
) -> None:
    with _connect() as connection:
        if last_alert_at is None:
            connection.execute(
                "UPDATE alert_subscriptions SET last_band = ? WHERE subscription_id = ?",
                (risk_band, subscription_id),
            )
        else:
            connection.execute(
                "UPDATE alert_subscriptions SET last_band = ?, last_alert_at = ? "
                "WHERE subscription_id = ?",
                (risk_band, last_alert_at, subscription_id),
            )


def get_risk_grid_cell_for_location(
    latitude: float, longitude: float
) -> dict[str, Any] | None:
    metadata = get_risk_grid_metadata()
    if metadata is None:
        return None
    grid_size_m = int(metadata["grid_size_m"])
    latitude_radius = (grid_size_m / 111_000) * 2
    longitude_radius = latitude_radius / max(abs(math.cos(math.radians(latitude))), 0.1)
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT * FROM risk_grid_cells
            WHERE grid_size_m = ?
                AND latitude BETWEEN ? AND ?
                AND longitude BETWEEN ? AND ?
            ORDER BY (latitude - ?) * (latitude - ?)
                + (longitude - ?) * (longitude - ?) * ?
            LIMIT 1
            """,
            (
                grid_size_m,
                latitude - latitude_radius,
                latitude + latitude_radius,
                longitude - longitude_radius,
                longitude + longitude_radius,
                latitude,
                latitude,
                longitude,
                longitude,
                math.cos(math.radians(latitude)) ** 2,
            ),
        ).fetchone()
    if row is None:
        return None
    cell = dict(row)
    cell["inputs"] = json.loads(cell.pop("inputs_json"))
    cell["geometry"] = json.loads(cell.pop("geometry_json"))
    return cell


def get_risk_grid_cell_for_district(state: str, district: str) -> dict[str, Any] | None:
    metadata = get_risk_grid_metadata()
    if metadata is None:
        return None
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT * FROM risk_grid_cells
            WHERE grid_size_m = ? AND lower(state) = lower(?)
                AND lower(district) = lower(?)
            ORDER BY risk_score DESC, updated_at DESC
            LIMIT 1
            """,
            (int(metadata["grid_size_m"]), state, district),
        ).fetchone()
    if row is None:
        return None
    cell = dict(row)
    cell["inputs"] = json.loads(cell.pop("inputs_json"))
    cell["geometry"] = json.loads(cell.pop("geometry_json"))
    return cell


def list_high_risk_grid_cells(
    bbox: tuple[float, float, float, float], limit: int = 5000
) -> list[dict[str, Any]]:
    metadata = get_risk_grid_metadata()
    if metadata is None:
        return []
    min_lon, min_lat, max_lon, max_lat = bbox
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM risk_grid_cells
            WHERE grid_size_m = ? AND risk_band = 'HIGH'
                AND longitude BETWEEN ? AND ?
                AND latitude BETWEEN ? AND ?
            ORDER BY risk_score DESC, updated_at DESC
            LIMIT ?
            """,
            (
                int(metadata["grid_size_m"]),
                min_lon,
                max_lon,
                min_lat,
                max_lat,
                limit,
            ),
        ).fetchall()
    cells = []
    for row in rows:
        cell = dict(row)
        cell["inputs"] = json.loads(cell.pop("inputs_json"))
        cell["geometry"] = json.loads(cell.pop("geometry_json"))
        cells.append(cell)
    return cells
