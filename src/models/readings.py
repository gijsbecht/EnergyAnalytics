from datetime import datetime

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

    # Voltage per phase (single-phase: one value; three-phase: three values)
    voltage_l1_v: float | None = Field(default=None)
    voltage_l2_v: float | None = Field(default=None)
    voltage_l3_v: float | None = Field(default=None)

    # Current per phase
    current_l1_a: float | None = Field(default=None)
    current_l2_a: float | None = Field(default=None)
    current_l3_a: float | None = Field(default=None)

    # Grid frequency
    frequency_hz: float | None = Field(default=None)

    # Energy counters (cumulative kWh from the meter)
    energy_import_t1_kwh: float = Field(description="Total imported energy tariff 1")
    energy_import_t2_kwh: float = Field(description="Total imported energy tariff 2")
    energy_export_t1_kwh: float = Field(description="Total exported energy tariff 1")
    energy_export_t2_kwh: float = Field(description="Total exported energy tariff 2")
