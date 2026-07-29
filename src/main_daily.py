"""Daily collection entry point for APSystems and EPEX datasets."""

import logging
import sys
from datetime import date, timedelta

from src.collectors.apsystems import APSystemsCollector
from src.collectors.epex import EPEXCollector
from src.config import load_apsystems_config, load_epex_config
from src.db import init_db, insert_apsystems_readings, insert_epex_readings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s - %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


def collect_daily() -> None:
    aps_config = load_apsystems_config()
    epex_config = load_epex_config()

    init_db(aps_config.db_path)

    target_date = date.today() - timedelta(days=1)

    aps_collector = APSystemsCollector(
        app_id=aps_config.app_id,
        app_secret=aps_config.app_secret,
        sid=aps_config.sid,
        ecu_id=aps_config.ecu_id,
        timeout_s=aps_config.timeout_s,
    )
    aps_readings = aps_collector.fetch_day(target_date)
    insert_apsystems_readings(aps_config.db_path, aps_readings)

    epex_collector = EPEXCollector(
        api_key=epex_config.parse_api_key,
        timeout_s=epex_config.timeout_s,
    )
    epex_readings = epex_collector.fetch_day(target_date)
    insert_epex_readings(epex_config.db_path, epex_readings)

    logger.info(
        "Stored %d APSystems rows and %d EPEX rows for %s",
        len(aps_readings),
        len(epex_readings),
        target_date.isoformat(),
    )


if __name__ == "__main__":
    try:
        collect_daily()
    except Exception:
        logger.exception("Daily collection failed")
        sys.exit(1)
