"""Entry point for the energy data collection service.

Designed to be invoked by a systemd timer every 5 minutes:

    uv run python -m src.main

Each invocation:
1. Loads config from environment variables
2. Initializes the database (idempotent)
3. Fetches a P1 reading from the HomeWizard meter
4. Persists the reading and updates hourly aggregates
"""

import logging
import sys

from src.collectors.homewizard import HomeWizardP1Collector
from src.config import load_config
from src.db import init_db, insert_p1_reading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s – %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


def collect_once() -> None:
    config = load_config()

    init_db(config.db_path)

    collector = HomeWizardP1Collector(
        host=config.homewizard_host,
        device_id=config.homewizard_device_id,
        timeout_s=config.homewizard_timeout_s,
    )

    reading = collector.fetch()
    insert_p1_reading(config.db_path, reading)

    logger.info(
        "Collected: %.1f W | import_t1=%.3f kWh | import_t2=%.3f kWh",
        reading.active_power_w,
        reading.total_power_import_t1_kwh,
        reading.total_power_import_t2_kwh,
    )


if __name__ == "__main__":
    try:
        collect_once()
    except Exception:
        logger.exception("Collection failed")
        sys.exit(1)
