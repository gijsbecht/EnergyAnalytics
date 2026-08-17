import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# Fresh schema version for this project iteration.
SCHEMA_VERSION = 1


def init_db(db_path: Path) -> None:
    """Initialize the database with the current schema.

    Idempotent: safe to call on every startup.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        current_version = conn.execute("PRAGMA user_version").fetchone()[0]
        logger.info("Database schema version: %d (target: %d)", current_version, SCHEMA_VERSION)

        # Enforce lightweight schema shape on every startup.
        conn.executescript("""
            DROP VIEW IF EXISTS energy_combined_5min;
            DROP VIEW IF EXISTS energy_combined_hourly;
            DROP VIEW IF EXISTS energy_hourly;
            DROP TABLE IF EXISTS energy_hourly;
        """)

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
            active_tariff              INTEGER,
            total_power_import_kwh     REAL    NOT NULL DEFAULT 0,
            total_power_import_t1_kwh  REAL    NOT NULL DEFAULT 0,
            total_power_import_t2_kwh  REAL    NOT NULL DEFAULT 0,
            total_power_export_kwh     REAL    NOT NULL DEFAULT 0,
            total_power_export_t1_kwh  REAL    NOT NULL DEFAULT 0,
            total_power_export_t2_kwh  REAL    NOT NULL DEFAULT 0,
            active_power_w REAL    NOT NULL,
            active_power_l1_w          REAL,
            active_voltage_l1_v        REAL,
            active_current_a           REAL,
            active_current_l1_a        REAL,
            voltage_sag_l1_count       INTEGER,
            voltage_swell_l1_count     INTEGER,
            any_power_fail_count       INTEGER,
            long_power_fail_count      INTEGER,
            total_gas_m3               REAL,
            gas_timestamp              INTEGER,
            created_at     INTEGER NOT NULL DEFAULT (CAST(strftime('%s', 'now') AS INTEGER))
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_source_device_time
            ON energy_readings (source_id, device_id, timestamp DESC);

        CREATE VIEW IF NOT EXISTS energy_hourly AS
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY source_id, device_id, CAST(((timestamp + 1800) / 3600) AS INTEGER)
                    ORDER BY ABS(timestamp - (CAST(((timestamp + 1800) / 3600) AS INTEGER) * 3600)),
                             timestamp DESC
                ) AS rn
            FROM energy_readings
        )
        SELECT er.*
        FROM energy_readings er
        JOIN ranked r ON r.id = er.id
        WHERE r.rn = 1;

        CREATE TABLE IF NOT EXISTS apsystems_readings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id   TEXT    NOT NULL,
            timestamp   INTEGER NOT NULL,
            energy_kwh  REAL    NOT NULL,
            created_at  INTEGER NOT NULL DEFAULT (CAST(strftime('%s', 'now') AS INTEGER))
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_apsystems_device_time
            ON apsystems_readings (device_id, timestamp);

        CREATE TABLE IF NOT EXISTS epex_spot_prices (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp      INTEGER NOT NULL,
            delivery_date  TEXT    NOT NULL,
            price_eur_mwh  REAL    NOT NULL,
            volume_total   REAL,
            created_at     INTEGER NOT NULL DEFAULT (CAST(strftime('%s', 'now') AS INTEGER))
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_epex_timestamp
            ON epex_spot_prices (timestamp);

        CREATE VIEW IF NOT EXISTS energy_combined_hourly AS
        SELECT
            CAST((eh.timestamp + 1800) / 3600 AS INTEGER) * 3600 AS hour_ts,
            eh.timestamp        AS p1_timestamp,
            eh.active_power_w,
            eh.active_tariff,
            eh.total_power_import_kwh,
            eh.total_power_import_t1_kwh,
            eh.total_power_import_t2_kwh,
            eh.total_power_export_kwh,
            eh.total_power_export_t1_kwh,
            eh.total_power_export_t2_kwh,
            eh.total_gas_m3,
            ar.energy_kwh       AS solar_energy_kwh,
            ep.price_eur_mwh    AS epex_price_eur_mwh,
            ep.volume_total     AS epex_volume_total
        FROM energy_hourly eh
        LEFT JOIN apsystems_readings ar
            ON CAST((eh.timestamp + 1800) / 3600 AS INTEGER) * 3600 = ar.timestamp
        LEFT JOIN epex_spot_prices ep
            ON CAST((eh.timestamp + 1800) / 3600 AS INTEGER) * 3600 = ep.timestamp
        WHERE eh.source_id = 'homewizard_p1';

        CREATE VIEW IF NOT EXISTS energy_combined_5min AS
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY source_id, device_id, CAST(((timestamp + 150) / 300) AS INTEGER)
                    ORDER BY ABS(timestamp - (CAST(((timestamp + 150) / 300) AS INTEGER) * 300)),
                             timestamp DESC
                ) AS rn
            FROM energy_readings
        ),
        energy_5min AS (
            SELECT er.*
            FROM energy_readings er
            JOIN ranked r ON r.id = er.id
            WHERE r.rn = 1
        )
        SELECT
            CAST((e5.timestamp + 150) / 300 AS INTEGER) * 300 AS five_min_ts,
            e5.timestamp        AS p1_timestamp,
            e5.active_power_w,
            e5.active_tariff,
            e5.total_power_import_kwh,
            e5.total_power_import_t1_kwh,
            e5.total_power_import_t2_kwh,
            e5.total_power_export_kwh,
            e5.total_power_export_t1_kwh,
            e5.total_power_export_t2_kwh,
            e5.total_gas_m3,
            ar.energy_kwh       AS solar_energy_kwh,
            ep.price_eur_mwh    AS epex_price_eur_mwh,
            ep.volume_total     AS epex_volume_total
        FROM energy_5min e5
        LEFT JOIN apsystems_readings ar
            ON CAST((e5.timestamp + 150) / 300 AS INTEGER) * 300 = ar.timestamp
        LEFT JOIN epex_spot_prices ep
            ON CAST((e5.timestamp + 1800) / 3600 AS INTEGER) * 3600 = ep.timestamp
        WHERE e5.source_id = 'homewizard_p1';
    """)
    logger.info("Migrated to schema version 1")
