from datetime import date, datetime

import requests

from src.models.readings import EPEXSpotReading

_EPEX_ENDPOINT = "https://euenergy.live/api/v1/prices"


class EPEXCollector:
    """Fetches EPEX NL day-ahead hourly spot prices."""

    def __init__(self, eu_energy_token: str, timeout_s: float = 10.0) -> None:
        self._eu_energy_token = eu_energy_token
        self._timeout_s = timeout_s

    def fetch_day(self, delivery_date: date) -> list[EPEXSpotReading]:
        """Fetch all hourly EPEX prices for a delivery date.

        Prices are requested for a single day in the NL zone.
        """
        try:
            response = requests.get(
                _EPEX_ENDPOINT,
                headers={"Authorization": f"Bearer {self._eu_energy_token}"},
                params={
                    "from": delivery_date.isoformat(),
                    "to": delivery_date.isoformat(),
                    "zone": "NL",
                },
                timeout=self._timeout_s,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ConnectionError(f"EPEX API request failed: {exc}") from exc

        payload = response.json()
        hours = payload.get("hours")
        if not isinstance(hours, list):
            raise ValueError(f"Invalid EPEX API payload: {payload}")

        payload_delivery_date = date.fromisoformat(
            payload.get("from", delivery_date.isoformat())
        )

        readings: list[EPEXSpotReading] = []
        for hour in hours:
            ts_raw = hour.get("ts")
            price_raw = hour.get("price")
            if ts_raw is None or price_raw is None:
                raise ValueError(f"Invalid EPEX API payload row: {hour}")

            timestamp = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).astimezone()
            readings.append(
                EPEXSpotReading(
                    timestamp=timestamp,
                    delivery_date=payload_delivery_date,
                    price_eur_mwh=float(price_raw),
                    volume_total=None,
                )
            )

        return readings
