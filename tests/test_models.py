from datetime import UTC, datetime

import pytest

from src.models.readings import APSystemsReading, EnergyReading, P1Reading


@pytest.fixture
def valid_p1_data() -> dict:
    return {
        "device_id": "p1-001",
        "timestamp": datetime(2026, 7, 22, 10, 0, 0, tzinfo=UTC),
        "active_tariff": 1,
        "active_power_w": -680.0,
        "active_power_l1_w": -686.0,
        "active_voltage_l1_v": 236.7,
        "active_current_a": 2.898,
        "active_current_l1_a": -2.898,
        "total_power_import_kwh": 5154.765,
        "total_power_import_t1_kwh": 2131.436,
        "total_power_import_t2_kwh": 3023.329,
        "total_power_export_kwh": 4963.836,
        "total_power_export_t1_kwh": 1542.177,
        "total_power_export_t2_kwh": 3421.659,
        "voltage_sag_l1_count": 12,
        "voltage_swell_l1_count": 1,
        "any_power_fail_count": 8,
        "long_power_fail_count": 5,
        "total_gas_m3": 2749.428,
        "gas_timestamp": 260726144003,
    }


class TestP1Reading:
    def test_valid_reading_parsed(self, valid_p1_data):
        reading = P1Reading(**valid_p1_data)
        assert reading.source_id == "homewizard_p1"
        assert reading.active_power_w == -680.0
        assert reading.active_voltage_l1_v == 236.7
        assert reading.total_power_import_t1_kwh == 2131.436

    def test_source_id_is_always_homewizard_p1(self, valid_p1_data):
        reading = P1Reading(**valid_p1_data)
        assert reading.source_id == "homewizard_p1"

    def test_negative_power_is_valid_for_export(self, valid_p1_data):
        valid_p1_data["active_power_w"] = -1.0
        reading = P1Reading(**valid_p1_data)
        assert reading.active_power_w == -1.0

    def test_default_source_id_applied(self, valid_p1_data):
        reading = P1Reading(**valid_p1_data)
        assert reading.source_id == "homewizard_p1"

    def test_optional_fields_can_be_none(self, valid_p1_data):
        valid_p1_data["active_current_a"] = None
        valid_p1_data["total_gas_m3"] = None
        valid_p1_data["gas_timestamp"] = None
        reading = P1Reading(**valid_p1_data)
        assert reading.active_current_a is None
        assert reading.total_gas_m3 is None

    def test_inherits_energy_reading(self, valid_p1_data):
        reading = P1Reading(**valid_p1_data)
        assert isinstance(reading, EnergyReading)

    def test_tariff_is_integer(self, valid_p1_data):
        valid_p1_data["active_tariff"] = 2
        reading = P1Reading(**valid_p1_data)
        assert reading.active_tariff == 2


class TestAPSystemsReading:
    @pytest.fixture
    def valid_apsystems_data(self) -> dict:
        return {
            "device_id": "ecu-001",
            "timestamp": datetime(2026, 7, 26, 10, 0, 0, tzinfo=UTC),
            "energy_kwh": 1.10,
            "active_power_w": 1100.0,
        }

    def test_valid_reading_parsed(self, valid_apsystems_data):
        reading = APSystemsReading(**valid_apsystems_data)
        assert reading.energy_kwh == pytest.approx(1.10)
        assert reading.active_power_w == pytest.approx(1100.0)

    def test_source_id_is_always_apsystems(self, valid_apsystems_data):
        reading = APSystemsReading(**valid_apsystems_data)
        assert reading.source_id == "apsystems"

    def test_device_id_stored(self, valid_apsystems_data):
        reading = APSystemsReading(**valid_apsystems_data)
        assert reading.device_id == "ecu-001"

    def test_zero_energy_kwh_is_valid(self, valid_apsystems_data):
        valid_apsystems_data["energy_kwh"] = 0.0
        valid_apsystems_data["active_power_w"] = 0.0
        reading = APSystemsReading(**valid_apsystems_data)
        assert reading.energy_kwh == 0.0

    def test_inherits_energy_reading(self, valid_apsystems_data):
        reading = APSystemsReading(**valid_apsystems_data)
        assert isinstance(reading, EnergyReading)
