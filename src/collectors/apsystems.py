import base64
import hashlib
import hmac
import logging
import uuid
from datetime import date, datetime
import re
from time import time

import requests

from src.models.readings import APSystemsReading

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.apsystemsema.com:9282"
_SIGNATURE_METHOD = "HmacSHA256"


class APSystemsCollector:
    """Fetches 5-minute solar energy data from the APSystems EMA API.

    One API call returns all available 5-minute readings for a given day.
    Does not extend CollectorBase because the fetch pattern is fundamentally
    different: a single request yields a list of readings rather than one.
    """

    def __init__(
        self, app_id: str, app_secret: str, sid: str, ecu_id: str, timeout_s: float = 10.0
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._sid = sid
        self._ecu_id = ecu_id
        self._timeout_s = timeout_s

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_day(self, target_date: date) -> list[APSystemsReading]:
        """Fetch all 5-minute energy readings for *target_date* (local time).

        Returns one APSystemsReading object per returned 5-minute timestamp.
        Hours with no production (e.g. nighttime) are included with energy_kwh=0.

        Raises:
            ConnectionError: when the HTTP request fails.
            ValueError: when the API returns a non-zero response code.
        """
        path = f"/user/api/v2/systems/{self._sid}/devices/ecu/energy/{self._ecu_id}"
        url = f"{_BASE_URL}{path}"
        date_str = target_date.strftime("%Y-%m-%d")

        try:
            response = requests.get(
                url,
                headers=self._build_headers(path),
                params={"energy_level": "minutely", "date_range": date_str},
                timeout=self._timeout_s,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ConnectionError(f"APSystems API request failed: {exc}") from exc

        payload = response.json()
        if payload.get("code") != 0:
            raise ValueError(f"APSystems API error code {payload.get('code')}: {payload}")

        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError(f"Expected payload.data object, got: {data}")

        raw_times = data.get("time")
        raw_energy = data.get("energy")
        raw_power = data.get("power")
        if not isinstance(raw_times, list) or not isinstance(raw_energy, list) or not isinstance(raw_power, list):
            raise ValueError("Expected payload.data.time, payload.data.energy, and payload.data.power lists")
        if not raw_times:
            raise ValueError("Expected at least one minutely value, got 0")
        if len(raw_times) != len(raw_energy) or len(raw_times) != len(raw_power):
            raise ValueError(
                "Expected equal number of time, energy, and power values, got "
                f"{len(raw_times)}, {len(raw_energy)}, and {len(raw_power)}"
            )

        readings: list[APSystemsReading] = []
        for time_label, energy_value, power_value in zip(raw_times, raw_energy, raw_power, strict=True):
            if not isinstance(time_label, str) or not re.fullmatch(r"\d{2}:\d{2}", time_label):
                raise ValueError(f"Invalid time entry '{time_label}', expected HH:MM")
            hour, minute = map(int, time_label.split(":"))
            if hour > 23 or minute > 59:
                raise ValueError(f"Invalid time entry '{time_label}', out of range")
            energy_kwh = float(energy_value)
            active_power_w = float(power_value)
            ts = datetime(
                target_date.year, target_date.month, target_date.day, hour, minute, 0
            ).astimezone()
            readings.append(
                APSystemsReading(
                    device_id=self._ecu_id,
                    timestamp=ts,
                    energy_kwh=energy_kwh,
                    active_power_w=active_power_w,
                )
            )

        logger.info(
            "Fetched %d minutely readings for %s - total %.3f kWh",
            len(readings),
            date_str,
            sum(r.energy_kwh for r in readings),
        )
        return readings

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_headers(self, request_path: str) -> dict[str, str]:
        timestamp = str(int(time() * 1000))
        nonce = uuid.uuid4().hex  # 32-char hex without dashes
        endpoint = request_path.split("/")[-1]
        string_to_sign = f"{timestamp}/{nonce}/{self._app_id}/{endpoint}/GET/{_SIGNATURE_METHOD}"
        signature = base64.b64encode(
            hmac.new(
                self._app_secret.encode(),
                string_to_sign.encode(),
                hashlib.sha256,
            ).digest()
        ).decode()
        return {
            "X-CA-AppId": self._app_id,
            "X-CA-Timestamp": timestamp,
            "X-CA-Nonce": nonce,
            "X-CA-Signature-Method": _SIGNATURE_METHOD,
            "X-CA-Signature": signature,
        }
