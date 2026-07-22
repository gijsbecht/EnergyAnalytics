from datetime import datetime

from pydantic import BaseModel, Field


class EnergyReading(BaseModel):
    """Generic reading shared across all energy sources."""

    source_id: str
    device_id: str
    timestamp: datetime
    active_power_w: float = Field(ge=0, description="Active power in watts")


class P1Reading(EnergyReading):
    """HomeWizard P1 meter reading.

    Extends EnergyReading with grid-specific measurements.
    source_id is always 'homewizard_p1'.
    """

    source_id: str = "homewizard_p1"

    # Voltage per phase (single-phase: one value; three-phase: three values)
    voltage_l1_v: float | None = Field(default=None, ge=0, le=300)
    voltage_l2_v: float | None = Field(default=None, ge=0, le=300)
    voltage_l3_v: float | None = Field(default=None, ge=0, le=300)

    # Current per phase
    current_l1_a: float | None = Field(default=None, ge=0)
    current_l2_a: float | None = Field(default=None, ge=0)
    current_l3_a: float | None = Field(default=None, ge=0)

    # Grid frequency
    frequency_hz: float | None = Field(default=None, ge=45, le=65)

    # Energy counters (cumulative kWh from the meter)
    energy_import_t1_kwh: float = Field(ge=0, description="Total imported energy tariff 1")
    energy_import_t2_kwh: float = Field(ge=0, description="Total imported energy tariff 2")
    energy_export_t1_kwh: float = Field(ge=0, description="Total exported energy tariff 1")
    energy_export_t2_kwh: float = Field(ge=0, description="Total exported energy tariff 2")
