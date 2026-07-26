import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.db.init import SCHEMA_VERSION, init_db
from src.db.queries import (
    get_daily_summary,
    insert_p1_reading,
)
from src.models.readings import P1Reading


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "test_energy.db"
    init_db(path)
    return path


def _make_reading(
    power_w: float = 1000.0,
    ts: datetime | None = None,
    import_t1: float = 100.0,
) -> P1Reading:
    return P1Reading(
        device_id="test-p1",
        timestamp=ts or datetime(2026, 7, 22, 10, 0, 0, tzinfo=UTC),
        active_tariff=1,
        active_power_w=power_w,
        active_power_l1_w=power_w,
        active_voltage_l1_v=230.0,
        active_current_a=4.35,
        active_current_l1_a=4.35,
        total_power_import_kwh=import_t1,
        total_power_import_t1_kwh=import_t1,
        total_power_import_t2_kwh=0.0,
        total_power_export_kwh=0.0,
        total_power_export_t1_kwh=0.0,
        total_power_export_t2_kwh=0.0,
        voltage_sag_l1_count=0,
        voltage_swell_l1_count=0,
        any_power_fail_count=0,
        long_power_fail_count=0,
    )


class TestInitDb:
    def test_creates_energy_readings_table(self, db_path):
        conn = sqlite3.connect(db_path)
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "energy_readings" in tables
        conn.close()

    def test_creates_energy_hourly_view(self, db_path):
        conn = sqlite3.connect(db_path)
        views = {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall()
        }
        assert "energy_hourly" in views
        conn.close()

    def test_no_cleanup_trigger_exists(self, db_path):
        conn = sqlite3.connect(db_path)
        triggers = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()
        }
        assert "cleanup_old_readings" not in triggers
        conn.close()

    def test_hourly_view_has_same_columns_as_energy_readings(self, db_path):
        conn = sqlite3.connect(db_path)
        table_cols = [r[1] for r in conn.execute("PRAGMA table_info(energy_readings)").fetchall()]
        view_cols = [r[1] for r in conn.execute("PRAGMA table_info(energy_hourly)").fetchall()]
        assert view_cols == table_cols
        conn.close()

    def test_schema_version_set(self, db_path):
        conn = sqlite3.connect(db_path)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == SCHEMA_VERSION
        conn.close()

    def test_idempotent_double_init(self, db_path):
        # Should not raise on second call
        init_db(db_path)
        conn = sqlite3.connect(db_path)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == SCHEMA_VERSION
        conn.close()

    def test_wal_mode_enabled(self, db_path):
        conn = sqlite3.connect(db_path)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
        conn.close()


class TestInsertP1Reading:
    def test_reading_stored(self, db_path):
        insert_p1_reading(db_path, _make_reading(power_w=1500.0))
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM energy_readings").fetchone()[0]
        assert count == 1
        conn.close()

    def test_reading_values_correct(self, db_path):
        insert_p1_reading(db_path, _make_reading(power_w=2000.0, import_t1=123.456))
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT active_power_w, total_power_import_t1_kwh FROM energy_readings"
        ).fetchone()
        assert row[0] == 2000.0
        assert row[1] == 123.456
        conn.close()

    def test_duplicate_timestamp_ignored(self, db_path):
        ts = datetime(2026, 7, 22, 10, 0, 0, tzinfo=UTC)
        insert_p1_reading(db_path, _make_reading(ts=ts))
        insert_p1_reading(db_path, _make_reading(ts=ts))
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM energy_readings").fetchone()[0]
        assert count == 1
        conn.close()

    def test_hourly_view_picks_closest_sample_to_hour(self, db_path):
        # 09:55 and 10:04 both map to 10:00 hour bucket; 10:04 is closer to 10:00.
        ts1 = datetime(2026, 7, 22, 9, 55, 0, tzinfo=UTC)
        ts2 = datetime(2026, 7, 22, 10, 4, 0, tzinfo=UTC)
        insert_p1_reading(db_path, _make_reading(power_w=800.0, ts=ts1))
        insert_p1_reading(db_path, _make_reading(power_w=1200.0, ts=ts2))
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT timestamp, active_power_w FROM energy_hourly "
            "WHERE source_id = ? AND device_id = ? ORDER BY timestamp LIMIT 1",
            ("homewizard_p1", "test-p1"),
        ).fetchone()
        assert row is not None
        assert row[0] == int(ts2.timestamp())
        assert row[1] == 1200.0
        conn.close()


class TestGetDailySummary:
    def test_returns_daily_rows(self, db_path):
        ts = datetime(2026, 7, 22, 10, 0, 0, tzinfo=UTC)
        insert_p1_reading(db_path, _make_reading(ts=ts))
        results = get_daily_summary(db_path, "homewizard_p1", 2026, 7)
        assert len(results) == 1
        assert results[0]["day"] == "2026-07-22"

    def test_returns_empty_for_different_month(self, db_path):
        ts = datetime(2026, 7, 22, 10, 0, 0, tzinfo=UTC)
        insert_p1_reading(db_path, _make_reading(ts=ts))
        results = get_daily_summary(db_path, "homewizard_p1", 2026, 6)
        assert results == []
