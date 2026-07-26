import logging
import time
from datetime import UTC, datetime

import requests

from src.collectors.base import CollectorBase
from src.models.readings import P1Reading

logger = logging.getLogger(__name__)

# HomeWizard Energy API v1 – local LAN endpoint (no authentication required)
_API_PATH = "/api/v1/data"

# Circuit breaker / retry settings
_MAX_RETRIES = 3
_INITIAL_BACKOFF_S = 1.0
_MAX_BACKOFF_S = 60.0
_CIRCUIT_COOLDOWN_S = 300  # 5 minutes after circuit opens


class HomeWizardP1Collector(CollectorBase):
    """Collects data from a HomeWizard P1 meter over local LAN.

    Implements exponential backoff and a simple circuit breaker so that a
    temporarily unreachable meter does not flood the logs or block the process.
    """

    def __init__(self, host: str, device_id: str, timeout_s: float = 5.0) -> None:
        self._url = f"http://{host}{_API_PATH}"
        self._device_id = device_id
        self._timeout_s = timeout_s

        self._consecutive_failures = 0
        self._circuit_open_until: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(self) -> P1Reading:
        """Fetch the latest P1 reading from the meter.

        Returns a validated P1Reading on success.
        Raises ConnectionError when the circuit is open or all retries fail.
        """
        if time.monotonic() < self._circuit_open_until:
            remaining = int(self._circuit_open_until - time.monotonic())
            raise ConnectionError(
                f"Circuit open – HomeWizard meter unreachable. Retrying in {remaining}s."
            )

        last_error: Exception | None = None
        backoff = _INITIAL_BACKOFF_S

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                data = self._get_json()
                reading = self._parse(data)
                self._consecutive_failures = 0
                return reading
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Attempt %d/%d failed: %s",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(min(backoff, _MAX_BACKOFF_S))
                    backoff *= 2

        self._consecutive_failures += 1
        if self._consecutive_failures >= _MAX_RETRIES:
            self._circuit_open_until = time.monotonic() + _CIRCUIT_COOLDOWN_S
            logger.error(
                "Circuit opened – %d consecutive failures. Pausing for %ds.",
                self._consecutive_failures,
                _CIRCUIT_COOLDOWN_S,
            )

        raise ConnectionError(
            f"HomeWizard P1 meter unreachable after {_MAX_RETRIES} attempts"
        ) from last_error

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_json(self) -> dict:
        response = requests.get(self._url, timeout=self._timeout_s)
        response.raise_for_status()
        return response.json()

    def _parse(self, data: dict) -> P1Reading:
        """Map the HomeWizard API v1 JSON response to a P1Reading."""
        return P1Reading(
            device_id=self._device_id,
            timestamp=datetime.now(UTC),
            active_power_w=data.get("active_power_w", 0.0),
            active_tariff=data.get("active_tariff"),
            total_power_import_kwh=data.get("total_power_import_kwh", 0.0),
            total_power_import_t1_kwh=data.get("total_power_import_t1_kwh", 0.0),
            total_power_import_t2_kwh=data.get("total_power_import_t2_kwh", 0.0),
            total_power_export_kwh=data.get("total_power_export_kwh", 0.0),
            total_power_export_t1_kwh=data.get("total_power_export_t1_kwh", 0.0),
            total_power_export_t2_kwh=data.get("total_power_export_t2_kwh", 0.0),
            active_power_l1_w=data.get("active_power_l1_w"),
            active_voltage_l1_v=data.get("active_voltage_l1_v"),
            active_current_a=data.get("active_current_a"),
            active_current_l1_a=data.get("active_current_l1_a"),
            voltage_sag_l1_count=data.get("voltage_sag_l1_count"),
            voltage_swell_l1_count=data.get("voltage_swell_l1_count"),
            any_power_fail_count=data.get("any_power_fail_count"),
            long_power_fail_count=data.get("long_power_fail_count"),
            total_gas_m3=data.get("total_gas_m3"),
            gas_timestamp=data.get("gas_timestamp"),
        )
