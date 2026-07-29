"""Entry point for the APSystems solar data collection service.

Designed to be invoked by a systemd timer once per day:

    uv run python -m src.main_apsystems

Each invocation:
1. Loads config from environment variables
2. Initializes the database (idempotent)
3. Fetches hourly solar energy readings for yesterday from the APSystems API
4. Persists all 24 readings (duplicate-safe)
"""

import logging
import sys
from datetime import date, timedelta

from src.collectors.apsystems import APSystemsCollector
from src.config import load_apsystems_config
from src.db import init_db, insert_apsystems_readings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s – %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


def collect_previous_day() -> None:
    config = load_apsystems_config()

    init_db(config.db_path)

    collector = APSystemsCollector(
        app_id=config.app_id,
        app_secret=config.app_secret,
        sid=config.sid,
        ecu_id=config.ecu_id,
        timeout_s=config.timeout_s,
    )

    yesterday = date.today() - timedelta(days=1)
    readings = collector.fetch_day(yesterday)
    insert_apsystems_readings(config.db_path, readings)

    total_kwh = sum(r.energy_kwh for r in readings)
    logger.info(
        "Stored %d hourly readings for %s – total solar production: %.3f kWh",
        len(readings),
        yesterday.isoformat(),
        total_kwh,
    )


if __name__ == "__main__":
    try:
        collect_previous_day()
    except Exception:
        logger.exception("APSystems collection failed")
        sys.exit(1)
