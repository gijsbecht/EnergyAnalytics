import logging
import sqlite3
from pathlib import Path

from src.models.readings import P1Reading

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
                active_power_w,
                voltage_l1_v, voltage_l2_v, voltage_l3_v,
                current_l1_a, current_l2_a, current_l3_a,
                frequency_hz,
                energy_import_t1_kwh, energy_import_t2_kwh,
                energy_export_t1_kwh, energy_export_t2_kwh
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reading.source_id,
                reading.device_id,
                ts,
                reading.active_power_w,
                reading.voltage_l1_v,
                reading.voltage_l2_v,
                reading.voltage_l3_v,
                reading.current_l1_a,
                reading.current_l2_a,
                reading.current_l3_a,
                reading.frequency_hz,
                reading.energy_import_t1_kwh,
                reading.energy_import_t2_kwh,
                reading.energy_export_t1_kwh,
                reading.energy_export_t2_kwh,
            ),
        )
        _upsert_hourly(conn, reading.source_id, reading.device_id, ts, reading.active_power_w)
        conn.commit()
        logger.debug("Inserted reading: %.1f W @ %s", reading.active_power_w, reading.timestamp)
    finally:
        conn.close()


def _upsert_hourly(
    conn: sqlite3.Connection,
    source_id: str,
    device_id: str,
    timestamp: int,
    power_w: float,
) -> None:
    """Upsert the hourly aggregate bucket that contains the given timestamp."""
    hour_start = (timestamp // 3600) * 3600

    existing = conn.execute(
        "SELECT avg_power_w, min_power_w, max_power_w, sample_count FROM energy_hourly "
        "WHERE source_id = ? AND device_id = ? AND hour_start = ?",
        (source_id, device_id, hour_start),
    ).fetchone()

    if existing is None:
        conn.execute(
            "INSERT INTO energy_hourly (source_id, device_id, hour_start, avg_power_w, "
            "min_power_w, max_power_w, sample_count) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (source_id, device_id, hour_start, power_w, power_w, power_w),
        )
    else:
        avg, min_p, max_p, count = existing
        new_count = count + 1
        new_avg = (avg * count + power_w) / new_count
        conn.execute(
            "UPDATE energy_hourly SET avg_power_w = ?, min_power_w = ?, max_power_w = ?, "
            "sample_count = ? WHERE source_id = ? AND device_id = ? AND hour_start = ?",
            (
                new_avg,
                min(min_p, power_w),
                max(max_p, power_w),
                new_count,
                source_id,
                device_id,
                hour_start,
            ),
        )


def get_latest_reading(db_path: Path, source_id: str) -> dict | None:
    """Return the most recent raw reading for a source as a dict."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM energy_readings WHERE source_id = ? ORDER BY timestamp DESC LIMIT 1",
            (source_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_hourly_aggregates(
    db_path: Path,
    source_id: str,
    start_ts: int,
    end_ts: int,
) -> list[dict]:
    """Return hourly aggregate rows between start_ts and end_ts (Unix timestamps)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM energy_hourly WHERE source_id = ? "
            "AND hour_start >= ? AND hour_start < ? ORDER BY hour_start",
            (source_id, start_ts, end_ts),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_daily_summary(db_path: Path, source_id: str, year: int, month: int) -> list[dict]:
    """Return daily energy sums (from hourly aggregates) for the given month."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                date(datetime(hour_start, 'unixepoch')) AS day,
                ROUND(AVG(avg_power_w), 2)              AS avg_power_w,
                ROUND(MIN(min_power_w), 2)              AS min_power_w,
                ROUND(MAX(max_power_w), 2)              AS max_power_w,
                SUM(sample_count)                       AS total_samples
            FROM energy_hourly
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
