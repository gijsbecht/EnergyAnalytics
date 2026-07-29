from datetime import UTC, date, datetime

import requests

from src.models.readings import EPEXSpotReading

_EPEX_ENDPOINT = (
    "https://api.parse.bot/scraper/"
    "f4c30fc5-0c2a-4b85-8bbe-e3ddda5e8775/get_market_results"
)


class EPEXCollector:
    """Fetches EPEX NL day-ahead hourly spot prices."""

    def __init__(self, api_key: str, timeout_s: float = 10.0) -> None:
        self._api_key = api_key
        self._timeout_s = timeout_s

    def fetch_day(self, delivery_date: date) -> list[EPEXSpotReading]:
        """Fetch all hourly EPEX prices for a delivery date.

        The API payload includes both `datetime` and `timestamp_ms` fields. We use
        `timestamp_ms` as the source of truth because it is unambiguous UTC epoch
        time and avoids timezone parsing issues.
        """
        try:
            response = requests.get(
                _EPEX_ENDPOINT,
                headers={"X-API-Key": self._api_key},
                params={
                    "auction": "MRC",
                    "product": "60",
                    "modality": "Auction",
                    "market_area": "NL",
                    "sub_modality": "DayAhead",
                    "delivery_date": delivery_date.isoformat(),
                },
                timeout=self._timeout_s,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ConnectionError(f"EPEX API request failed: {exc}") from exc

        payload = response.json()
        if payload.get("status") != "success":
            raise ValueError(f"EPEX API error: {payload}")

        data = payload.get("data", {})
        results = data.get("results", [])
        payload_delivery_date = date.fromisoformat(
            data.get("delivery_date", delivery_date.isoformat())
        )

        readings: list[EPEXSpotReading] = []
        for result in results:
            ts_s = int(result["timestamp_ms"] / 1000)
            timestamp = datetime.fromtimestamp(ts_s, tz=UTC).astimezone()
            readings.append(
                EPEXSpotReading(
                    timestamp=timestamp,
                    delivery_date=payload_delivery_date,
                    price_eur_mwh=float(result["price"]),
                    volume_total=result.get("volume_total"),
                )
            )

        return readings
