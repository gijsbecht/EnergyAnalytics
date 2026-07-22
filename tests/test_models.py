from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.models.readings import EnergyReading, P1Reading


@pytest.fixture
def valid_p1_data() -> dict:
    return {
        "device_id": "p1-001",
        "timestamp": datetime(2026, 7, 22, 10, 0, 0, tzinfo=UTC),
        "active_power_w": 1234.5,
        "voltage_l1_v": 231.0,
        "voltage_l2_v": 230.5,
        "voltage_l3_v": 232.0,
        "current_l1_a": 5.3,
        "current_l2_a": 5.1,
        "current_l3_a": 5.4,
        "frequency_hz": 50.01,
        "energy_import_t1_kwh": 1000.0,
        "energy_import_t2_kwh": 500.0,
        "energy_export_t1_kwh": 0.0,
        "energy_export_t2_kwh": 0.0,
    }


class TestP1Reading:
    def test_valid_reading_parsed(self, valid_p1_data):
        reading = P1Reading(**valid_p1_data)
        assert reading.source_id == "homewizard_p1"
        assert reading.active_power_w == 1234.5
        assert reading.voltage_l1_v == 231.0
        assert reading.energy_import_t1_kwh == 1000.0

    def test_source_id_is_always_homewizard_p1(self, valid_p1_data):
        reading = P1Reading(**valid_p1_data)
        assert reading.source_id == "homewizard_p1"

    def test_negative_power_rejected(self, valid_p1_data):
        valid_p1_data["active_power_w"] = -1.0
        with pytest.raises(ValidationError):
            P1Reading(**valid_p1_data)

    def test_voltage_too_high_rejected(self, valid_p1_data):
        valid_p1_data["voltage_l1_v"] = 350.0
        with pytest.raises(ValidationError):
            P1Reading(**valid_p1_data)

    def test_voltage_negative_rejected(self, valid_p1_data):
        valid_p1_data["voltage_l1_v"] = -1.0
        with pytest.raises(ValidationError):
            P1Reading(**valid_p1_data)

    def test_frequency_out_of_range_rejected(self, valid_p1_data):
        valid_p1_data["frequency_hz"] = 100.0
        with pytest.raises(ValidationError):
            P1Reading(**valid_p1_data)

    def test_negative_energy_counter_rejected(self, valid_p1_data):
        valid_p1_data["energy_import_t1_kwh"] = -0.001
        with pytest.raises(ValidationError):
            P1Reading(**valid_p1_data)

    def test_optional_phase_fields_can_be_none(self, valid_p1_data):
        valid_p1_data.pop("voltage_l2_v")
        valid_p1_data.pop("voltage_l3_v")
        valid_p1_data.pop("current_l2_a")
        valid_p1_data.pop("current_l3_a")
        reading = P1Reading(**valid_p1_data)
        assert reading.voltage_l2_v is None
        assert reading.voltage_l3_v is None

    def test_inherits_energy_reading(self, valid_p1_data):
        reading = P1Reading(**valid_p1_data)
        assert isinstance(reading, EnergyReading)

    def test_zero_power_is_valid(self, valid_p1_data):
        valid_p1_data["active_power_w"] = 0.0
        reading = P1Reading(**valid_p1_data)
        assert reading.active_power_w == 0.0
