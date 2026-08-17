from datetime import date, datetime

from pydantic import BaseModel, Field


class EnergyReading(BaseModel):
    """Generic reading shared across all energy sources."""

    source_id: str
    device_id: str
    timestamp: datetime
    active_power_w: float = Field(description="Active power in watts")


class P1Reading(EnergyReading):
    """HomeWizard P1 meter reading.

    Extends EnergyReading with grid-specific measurements.
    source_id is always 'homewizard_p1'.
    """

    source_id: str = "homewizard_p1"

    active_tariff: int | None = Field(default=None)

    # Cumulative import/export counters in kWh
    total_power_import_kwh: float = Field(default=0.0)
    total_power_import_t1_kwh: float = Field(default=0.0)
    total_power_import_t2_kwh: float = Field(default=0.0)
    total_power_export_kwh: float = Field(default=0.0)
    total_power_export_t1_kwh: float = Field(default=0.0)
    total_power_export_t2_kwh: float = Field(default=0.0)

    # Instantaneous values
    active_power_l1_w: float | None = Field(default=None)
    active_voltage_l1_v: float | None = Field(default=None)
    active_current_a: float | None = Field(default=None)
    active_current_l1_a: float | None = Field(default=None)

    # Meter counters
    voltage_sag_l1_count: int | None = Field(default=None)
    voltage_swell_l1_count: int | None = Field(default=None)
    any_power_fail_count: int | None = Field(default=None)
    long_power_fail_count: int | None = Field(default=None)

    # Gas meter values (if external gas meter is paired)
    total_gas_m3: float | None = Field(default=None)
    gas_timestamp: int | None = Field(default=None)


class APSystemsReading(EnergyReading):
    """APSystems solar inverter interval energy reading.

    One reading per interval of the day, fetched in a single daily API call.
    source_id is always 'apsystems'.
    active_power_w represents average watts for the interval.
    """

    source_id: str = "apsystems"

    # Solar energy production for this interval in kWh
    energy_kwh: float = Field(description="Solar energy produced during this interval in kWh")


class EPEXSpotReading(BaseModel):
    """Day-ahead EPEX spot price for a single hour."""

    timestamp: datetime
    delivery_date: date
    price_eur_mwh: float
    volume_total: float | None = Field(default=None)
