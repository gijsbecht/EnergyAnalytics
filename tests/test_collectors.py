import time
from unittest.mock import MagicMock, patch

import pytest

from src.collectors.homewizard import HomeWizardP1Collector
from src.models.readings import P1Reading

_VALID_API_RESPONSE = {
    "active_power_w": 1234.5,
    "active_voltage_l1_v": 231.0,
    "active_voltage_l2_v": 230.5,
    "active_voltage_l3_v": 232.0,
    "active_current_l1_a": 5.3,
    "active_current_l2_a": 5.1,
    "active_current_l3_a": 5.4,
    "active_frequency_hz": 50.01,
    "total_power_import_t1_kwh": 1000.0,
    "total_power_import_t2_kwh": 500.0,
    "total_power_export_t1_kwh": 0.0,
    "total_power_export_t2_kwh": 0.0,
}


@pytest.fixture
def collector() -> HomeWizardP1Collector:
    return HomeWizardP1Collector(host="192.168.1.100", device_id="p1-test")


class TestHomeWizardP1Collector:
    def test_successful_fetch_returns_p1_reading(self, collector):
        mock_response = MagicMock()
        mock_response.json.return_value = _VALID_API_RESPONSE
        mock_response.raise_for_status = MagicMock()

        with patch("src.collectors.homewizard.requests.get", return_value=mock_response):
            reading = collector.fetch()

        assert isinstance(reading, P1Reading)
        assert reading.active_power_w == 1234.5
        assert reading.source_id == "homewizard_p1"
        assert reading.device_id == "p1-test"

    def test_voltage_and_frequency_parsed(self, collector):
        mock_response = MagicMock()
        mock_response.json.return_value = _VALID_API_RESPONSE
        mock_response.raise_for_status = MagicMock()

        with patch("src.collectors.homewizard.requests.get", return_value=mock_response):
            reading = collector.fetch()

        assert reading.voltage_l1_v == 231.0
        assert reading.frequency_hz == pytest.approx(50.01)

    def test_energy_counters_parsed(self, collector):
        mock_response = MagicMock()
        mock_response.json.return_value = _VALID_API_RESPONSE
        mock_response.raise_for_status = MagicMock()

        with patch("src.collectors.homewizard.requests.get", return_value=mock_response):
            reading = collector.fetch()

        assert reading.energy_import_t1_kwh == 1000.0
        assert reading.energy_export_t1_kwh == 0.0

    def test_connection_error_retries_and_raises(self, collector):
        with (
            patch("src.collectors.homewizard.requests.get", side_effect=ConnectionError("timeout")),
            patch("src.collectors.homewizard.time.sleep"),  # avoid actual sleeping in tests
        ):
            with pytest.raises(ConnectionError):
                collector.fetch()

    def test_retries_correct_number_of_times(self, collector):
        with (
            patch(
                "src.collectors.homewizard.requests.get", side_effect=ConnectionError("fail")
            ) as mock_get,
            patch("src.collectors.homewizard.time.sleep"),
        ):
            with pytest.raises(ConnectionError):
                collector.fetch()

        assert mock_get.call_count == 3  # _MAX_RETRIES

    def test_circuit_opens_after_repeated_failures(self, collector):
        # The circuit opens after _MAX_RETRIES (3) consecutive *fetch calls* all fail.
        # Each fetch call already retries internally, so 3 failed fetches = circuit open.
        with (
            patch("src.collectors.homewizard.requests.get", side_effect=ConnectionError("fail")),
            patch("src.collectors.homewizard.time.sleep"),
        ):
            for _ in range(3):
                with pytest.raises(ConnectionError):
                    collector.fetch()

        # Circuit should now be open – next call raises immediately without HTTP attempt
        with pytest.raises(ConnectionError, match="Circuit open"):
            collector.fetch()

    def test_circuit_reopens_after_cooldown(self, collector):
        mock_response = MagicMock()
        mock_response.json.return_value = _VALID_API_RESPONSE
        mock_response.raise_for_status = MagicMock()

        with (
            patch("src.collectors.homewizard.requests.get", side_effect=ConnectionError("fail")),
            patch("src.collectors.homewizard.time.sleep"),
        ):
            with pytest.raises(ConnectionError):
                collector.fetch()

        # Fast-forward time past the cooldown
        collector._circuit_open_until = time.monotonic() - 1

        with patch("src.collectors.homewizard.requests.get", return_value=mock_response):
            reading = collector.fetch()

        assert reading.active_power_w == 1234.5

    def test_http_error_triggers_retry(self, collector):
        import requests as req

        error_response = MagicMock()
        error_response.raise_for_status.side_effect = req.exceptions.HTTPError("503")

        with (
            patch("src.collectors.homewizard.requests.get", return_value=error_response),
            patch("src.collectors.homewizard.time.sleep"),
        ):
            with pytest.raises(ConnectionError):
                collector.fetch()

    def test_successful_fetch_resets_failure_count(self, collector):
        mock_response = MagicMock()
        mock_response.json.return_value = _VALID_API_RESPONSE
        mock_response.raise_for_status = MagicMock()

        with (
            patch("src.collectors.homewizard.requests.get", side_effect=ConnectionError("fail")),
            patch("src.collectors.homewizard.time.sleep"),
        ):
            with pytest.raises(ConnectionError):
                collector.fetch()

        collector._circuit_open_until = time.monotonic() - 1

        with patch("src.collectors.homewizard.requests.get", return_value=mock_response):
            collector.fetch()

        assert collector._consecutive_failures == 0

    def test_missing_optional_fields_default_to_none(self, collector):
        minimal_response = {
            "active_power_w": 500.0,
            "total_power_import_t1_kwh": 50.0,
            "total_power_import_t2_kwh": 0.0,
            "total_power_export_t1_kwh": 0.0,
            "total_power_export_t2_kwh": 0.0,
        }
        mock_response = MagicMock()
        mock_response.json.return_value = minimal_response
        mock_response.raise_for_status = MagicMock()

        with patch("src.collectors.homewizard.requests.get", return_value=mock_response):
            reading = collector.fetch()

        assert reading.voltage_l1_v is None
        assert reading.frequency_hz is None
        assert reading.active_power_w == 500.0
