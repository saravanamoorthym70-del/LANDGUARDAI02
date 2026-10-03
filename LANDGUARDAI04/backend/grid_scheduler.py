import logging
import os
import time

from backend.record_store import init_db
from backend.risk_grid import run_grid_update
from backend.telegram_alerts import dispatch_high_risk_alerts


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    interval_hours = float(os.getenv("LANDGUARD_GRID_INTERVAL_HOURS", "6"))
    if interval_hours <= 0:
        raise ValueError("LANDGUARD_GRID_INTERVAL_HOURS must be positive")

    logger = logging.getLogger(__name__)
    logger.info("Starting regional risk-grid scheduler; interval=%s hours", interval_hours)
    while True:
        try:
            init_db()
            summary = run_grid_update(
                cell_size_m=int(os.getenv("LANDGUARD_GRID_CELL_SIZE_M", "1000")),
                batch_size=int(os.getenv("LANDGUARD_GRID_BATCH_SIZE", "200")),
                cache_hours=float(os.getenv("LANDGUARD_GRID_CACHE_HOURS", "4")),
                request_interval_seconds=float(
                    os.getenv("LANDGUARD_GRID_REQUEST_INTERVAL_SECONDS", "2")
                ),
            )
            if summary["complete"]:
                dispatch_high_risk_alerts()
        except Exception:
            logger.exception("Scheduled risk-grid update failed; retaining stored results")
        time.sleep(interval_hours * 60 * 60)


if __name__ == "__main__":
    main()