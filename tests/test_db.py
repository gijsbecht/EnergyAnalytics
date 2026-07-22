import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.db.init import SCHEMA_VERSION, init_db
from src.db.queries import (
    get_daily_summary,
    get_hourly_aggregates,
    get_latest_reading,
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
        active_power_w=power_w,
        voltage_l1_v=230.0,
        frequency_hz=50.0,
        energy_import_t1_kwh=import_t1,
        energy_import_t2_kwh=0.0,
        energy_export_t1_kwh=0.0,
        energy_export_t2_kwh=0.0,
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

    def test_creates_energy_hourly_table(self, db_path):
        conn = sqlite3.connect(db_path)
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "energy_hourly" in tables
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
            "SELECT active_power_w, energy_import_t1_kwh FROM energy_readings"
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

    def test_hourly_aggregate_created(self, db_path):
        insert_p1_reading(db_path, _make_reading(power_w=1000.0))
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM energy_hourly").fetchone()[0]
        assert count == 1
        conn.close()

    def test_hourly_aggregate_updated_on_second_reading(self, db_path):
        ts1 = datetime(2026, 7, 22, 10, 0, 0, tzinfo=UTC)
        ts2 = datetime(2026, 7, 22, 10, 15, 0, tzinfo=UTC)
        insert_p1_reading(db_path, _make_reading(power_w=1000.0, ts=ts1))
        insert_p1_reading(db_path, _make_reading(power_w=2000.0, ts=ts2))
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT avg_power_w, min_power_w, max_power_w, sample_count FROM energy_hourly"
        ).fetchone()
        assert row[3] == 2  # sample_count
        assert row[1] == 1000.0  # min
        assert row[2] == 2000.0  # max
        assert row[0] == pytest.approx(1500.0)  # avg
        conn.close()

    def test_different_hours_create_separate_rows(self, db_path):
        ts1 = datetime(2026, 7, 22, 10, 0, 0, tzinfo=UTC)
        ts2 = datetime(2026, 7, 22, 11, 0, 0, tzinfo=UTC)
        insert_p1_reading(db_path, _make_reading(ts=ts1))
        insert_p1_reading(db_path, _make_reading(ts=ts2))
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM energy_hourly").fetchone()[0]
        assert count == 2
        conn.close()


class TestGetLatestReading:
    def test_returns_none_when_empty(self, db_path):
        result = get_latest_reading(db_path, "homewizard_p1")
        assert result is None

    def test_returns_most_recent(self, db_path):
        ts1 = datetime(2026, 7, 22, 9, 0, 0, tzinfo=UTC)
        ts2 = datetime(2026, 7, 22, 10, 0, 0, tzinfo=UTC)
        insert_p1_reading(db_path, _make_reading(power_w=500.0, ts=ts1))
        insert_p1_reading(db_path, _make_reading(power_w=900.0, ts=ts2))
        result = get_latest_reading(db_path, "homewizard_p1")
        assert result is not None
        assert result["active_power_w"] == 900.0


class TestGetHourlyAggregates:
    def test_returns_aggregates_in_range(self, db_path):
        ts = datetime(2026, 7, 22, 10, 0, 0, tzinfo=UTC)
        insert_p1_reading(db_path, _make_reading(ts=ts))
        start = int(datetime(2026, 7, 22, 0, 0, tzinfo=UTC).timestamp())
        end = int(datetime(2026, 7, 23, 0, 0, tzinfo=UTC).timestamp())
        results = get_hourly_aggregates(db_path, "homewizard_p1", start, end)
        assert len(results) == 1
        assert results[0]["sample_count"] == 1

    def test_returns_empty_outside_range(self, db_path):
        ts = datetime(2026, 7, 22, 10, 0, 0, tzinfo=UTC)
        insert_p1_reading(db_path, _make_reading(ts=ts))
        start = int(datetime(2026, 7, 23, 0, 0, tzinfo=UTC).timestamp())
        end = int(datetime(2026, 7, 24, 0, 0, tzinfo=UTC).timestamp())
        results = get_hourly_aggregates(db_path, "homewizard_p1", start, end)
        assert results == []


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
