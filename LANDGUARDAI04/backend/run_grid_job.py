import argparse
import json
import logging
import os

from backend.record_store import init_db
from backend.risk_grid import run_grid_update
from backend.telegram_alerts import dispatch_high_risk_alerts


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and score the LANDGUARD regional risk grid")
    parser.add_argument(
        "--cell-size-m",
        type=int,
        default=int(os.getenv("LANDGUARD_GRID_CELL_SIZE_M", "1000")),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("LANDGUARD_GRID_BATCH_SIZE", "200")),
    )
    parser.add_argument(
        "--cache-hours",
        type=float,
        default=float(os.getenv("LANDGUARD_GRID_CACHE_HOURS", "4")),
    )
    parser.add_argument(
        "--request-interval-seconds",
        type=float,
        default=float(os.getenv("LANDGUARD_GRID_REQUEST_INTERVAL_SECONDS", "2")),
    )
    parser.add_argument(
        "--max-cells",
        type=int,
        help="Process only this many cells; intended for live-data smoke checks.",
    )
    parser.add_argument(
        "--no-store",
        action="store_true",
        help="Fetch and score a sample without changing the SQLite grid.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    init_db()
    summary = run_grid_update(
        cell_size_m=args.cell_size_m,
        batch_size=args.batch_size,
        cache_hours=args.cache_hours,
        request_interval_seconds=args.request_interval_seconds,
        max_cells=args.max_cells,
        persist=not args.no_store,
    )
    if summary["complete"]:
        summary["alerts"] = dispatch_high_risk_alerts()
    print(json.dumps(summary, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()