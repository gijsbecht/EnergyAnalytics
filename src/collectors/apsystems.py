import base64
import hashlib
import hmac
import logging
import uuid
from datetime import date, datetime
from time import time

import requests

from src.models.readings import APSystemsReading

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.apsystemsema.com:9282"
_SIGNATURE_METHOD = "HmacSHA256"


class APSystemsCollector:
    """Fetches hourly solar energy data from the APSystems EMA API.

    One API call returns all 24 hourly readings for a given day.
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
        """Fetch all 24 hourly energy readings for *target_date* (local time).

        Returns a list of 24 APSystemsReading objects, one per hour (00–23).
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
                params={"energy_level": "hourly", "date_range": date_str},
                timeout=self._timeout_s,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ConnectionError(f"APSystems API request failed: {exc}") from exc

        payload = response.json()
        if payload.get("code") != 0:
            raise ValueError(f"APSystems API error code {payload.get('code')}: {payload}")

        raw_data: list = payload.get("data", [])
        if len(raw_data) != 24:
            raise ValueError(f"Expected 24 hourly values, got {len(raw_data)}: {raw_data}")

        readings: list[APSystemsReading] = []
        for hour, value in enumerate(raw_data):
            energy_kwh = float(value)
            # Construct a local-time datetime for the start of this hour, then
            # attach the local timezone so .timestamp() converts to UTC correctly.
            ts = datetime(
                target_date.year, target_date.month, target_date.day, hour, 0, 0
            ).astimezone()
            readings.append(
                APSystemsReading(
                    device_id=self._ecu_id,
                    timestamp=ts,
                    energy_kwh=energy_kwh,
                    active_power_w=energy_kwh * 1000.0,
                )
            )

        logger.info(
            "Fetched %d hourly readings for %s – total %.3f kWh",
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
