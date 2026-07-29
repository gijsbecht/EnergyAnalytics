import logging
import sqlite3
from pathlib import Path

from src.models.readings import APSystemsReading, P1Reading

logger = logging.getLogger(__name__)


def insert_p1_reading(db_path: Path, reading: P1Reading) -> None:
    """Insert a P1 reading and upsert the corresponding hourly aggregate."""
    conn = sqlite3.connect(db_path)
    try:
        ts = int(reading.timestamp.timestamp())
        conn.execute(
            """
            INSERT OR IGNORE INTO energy_readings (
                source_id, device_id, timestamp,
                active_tariff,
                total_power_import_kwh, total_power_import_t1_kwh, total_power_import_t2_kwh,
                total_power_export_kwh, total_power_export_t1_kwh, total_power_export_t2_kwh,
                active_power_w,
                active_power_l1_w,
                active_voltage_l1_v,
                active_current_a,
                active_current_l1_a,
                voltage_sag_l1_count,
                voltage_swell_l1_count,
                any_power_fail_count,
                long_power_fail_count,
                total_gas_m3,
                gas_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reading.source_id,
                reading.device_id,
                ts,
                reading.active_tariff,
                reading.total_power_import_kwh,
                reading.total_power_import_t1_kwh,
                reading.total_power_import_t2_kwh,
                reading.total_power_export_kwh,
                reading.total_power_export_t1_kwh,
                reading.total_power_export_t2_kwh,
                reading.active_power_w,
                reading.active_power_l1_w,
                reading.active_voltage_l1_v,
                reading.active_current_a,
                reading.active_current_l1_a,
                reading.voltage_sag_l1_count,
                reading.voltage_swell_l1_count,
                reading.any_power_fail_count,
                reading.long_power_fail_count,
                reading.total_gas_m3,
                reading.gas_timestamp,
            ),
        )
        conn.commit()
        logger.debug("Inserted reading: %.1f W @ %s", reading.active_power_w, reading.timestamp)
    finally:
        conn.close()


def get_daily_summary(db_path: Path, source_id: str, year: int, month: int) -> list[dict]:
    """Return daily power summary from the hourly closest-sample view."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                date(datetime(hour_start, 'unixepoch')) AS day,
                ROUND(AVG(active_power_w), 2)           AS avg_power_w,
                ROUND(MIN(active_power_w), 2)           AS min_power_w,
                ROUND(MAX(active_power_w), 2)           AS max_power_w,
                COUNT(*)                                AS total_samples
            FROM (
                SELECT
                    CAST(((timestamp + 1800) / 3600) AS INTEGER) * 3600 AS hour_start,
                    active_power_w,
                    source_id
                FROM energy_hourly
            )
            WHERE source_id = ?
              AND strftime('%Y', datetime(hour_start, 'unixepoch')) = ?
              AND strftime('%m', datetime(hour_start, 'unixepoch')) = ?
            GROUP BY day
            ORDER BY day
            """,
            (source_id, str(year), f"{month:02d}"),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def insert_apsystems_readings(db_path: Path, readings: list[APSystemsReading]) -> None:
    """Batch-insert hourly APSystems readings. Duplicate timestamps are silently ignored."""
    if not readings:
        return
    conn = sqlite3.connect(db_path)
    try:
        conn.executemany(
            """
            INSERT OR IGNORE INTO apsystems_readings (device_id, timestamp, energy_kwh)
            VALUES (?, ?, ?)
            """,
            [
                (r.device_id, int(r.timestamp.timestamp()), r.energy_kwh)
                for r in readings
            ],
        )
        conn.commit()
        logger.debug("Inserted %d APSystems readings", len(readings))
    finally:
        conn.close()
