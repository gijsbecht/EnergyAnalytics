import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# Bump this when adding schema changes; add a migration block below.
SCHEMA_VERSION = 1


def init_db(db_path: Path) -> None:
    """Initialize the database, applying migrations if needed.

    Idempotent: safe to call on every startup.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        current_version = conn.execute("PRAGMA user_version").fetchone()[0]
        logger.info("Database schema version: %d (target: %d)", current_version, SCHEMA_VERSION)

        if current_version < 1:
            _migrate_v1(conn)

        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
        logger.info("Database initialized at %s", db_path)
    finally:
        conn.close()


def _migrate_v1(conn: sqlite3.Connection) -> None:
    """Initial schema: raw readings + hourly aggregates."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS energy_readings (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id      TEXT    NOT NULL,
            device_id      TEXT    NOT NULL,
            timestamp      INTEGER NOT NULL,
            active_power_w REAL    NOT NULL,
            voltage_l1_v   REAL,
            voltage_l2_v   REAL,
            voltage_l3_v   REAL,
            current_l1_a   REAL,
            current_l2_a   REAL,
            current_l3_a   REAL,
            frequency_hz   REAL,
            energy_import_t1_kwh REAL NOT NULL DEFAULT 0,
            energy_import_t2_kwh REAL NOT NULL DEFAULT 0,
            energy_export_t1_kwh REAL NOT NULL DEFAULT 0,
            energy_export_t2_kwh REAL NOT NULL DEFAULT 0,
            created_at     INTEGER NOT NULL DEFAULT (CAST(strftime('%s', 'now') AS INTEGER))
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_source_device_time
            ON energy_readings (source_id, device_id, timestamp DESC);

        CREATE TABLE IF NOT EXISTS energy_hourly (
            source_id      TEXT    NOT NULL,
            device_id      TEXT    NOT NULL,
            hour_start     INTEGER NOT NULL,
            avg_power_w    REAL    NOT NULL,
            min_power_w    REAL    NOT NULL,
            max_power_w    REAL    NOT NULL,
            sample_count   INTEGER NOT NULL,
            PRIMARY KEY (source_id, device_id, hour_start)
        );

        CREATE INDEX IF NOT EXISTS idx_hourly_source_device_hour
            ON energy_hourly (source_id, device_id, hour_start DESC);

        -- Auto-delete raw readings older than 7 days after each insert.
        CREATE TRIGGER IF NOT EXISTS cleanup_old_readings
        AFTER INSERT ON energy_readings
        BEGIN
            DELETE FROM energy_readings
            WHERE created_at < (CAST(strftime('%s', 'now') AS INTEGER) - 604800);
        END;
    """)
    logger.info("Migrated to schema version 1")
