from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pypsa

from utils import show_interactive_lines

CSV_PATH = './energy_combined_5min.csv'
START_DATE = '2026-08-18'
END_DATE = '2026-08-22'

VAT = 0.21
FIXED_NETWORK_TARIFF = 0.1058  # €/kWh, fixed network tariff for residential grid connection
INTERVAL_MINUTES = 5
DT_HOURS = INTERVAL_MINUTES / 60.0

# --- Battery configuration ---
BATTERY_POWER_KW = 0.8       # max charge/discharge rate
BATTERY_CAPACITY_KWH = 2.7   # usable energy capacity
BATTERY_EFFICIENCY = 0.70    # round-trip; split symmetrically per side
BATTERY_EFF_SIDE = np.sqrt(BATTERY_EFFICIENCY)
GRID_MAX_KW = 25.0           # residential grid connection limit


# --- Data preparation for PyPSA ---
df = pd.read_csv(CSV_PATH)

# Add datetime index and sort
df['datetime'] = df['five_min_ts'].apply(lambda x: datetime.fromtimestamp(x))
df = df.sort_values(by='datetime', ascending=True)
df = df.set_index('datetime')
df.index = pd.DatetimeIndex(df.index)

# Filter date range
df = df.loc[START_DATE:END_DATE]

# Add delta columns for power import/export and total usage
df['delta_power_import_kwh'] = df['total_power_import_kwh'].diff()
df['delta_power_export_kwh'] = df['total_power_export_kwh'].diff()
df['delta_power_total_kwh'] = df['delta_power_import_kwh'] - df['delta_power_export_kwh']

# Clean up data: fill missing solar/usage with 0, drop rows where price is unknown, clip negatives
df['delta_power_import_kwh'] = df['delta_power_import_kwh'].fillna(0)
df['delta_power_export_kwh'] = df['delta_power_export_kwh'].fillna(0)
df['delta_power_total_kwh'] = df['delta_power_total_kwh'].fillna(0)
df['solar_energy_kwh'] = df['solar_energy_kwh'].fillna(0).clip(lower=0)
df['power_usage_kwh'] = df['delta_power_total_kwh'] + df['solar_energy_kwh']
df['power_usage_kwh'] = df['power_usage_kwh'].clip(lower=0)
df = df.dropna(subset=['epex_price_eur_mwh'])

# Interactive plot: delta power import/export and total usage
# show_interactive_lines(
# 	df,
# 	title='Delta Power Import/Export and Total Usage',
# 	y_label='Energy (kWh)',
# 	series_map=[
# 		('Delta Power Import (kWh)', 'delta_power_import_kwh'),
# 		('Delta Power Export (kWh)', 'delta_power_export_kwh'),
# 		('Delta Power Total (kWh)', 'delta_power_total_kwh'),
# 		('Solar Energy (kWh)', 'solar_energy_kwh'),
# 	],
# )

# Interactive plot: solar energy and power usage
# show_interactive_lines(
# 	df,
# 	title='Solar Energy and Power Usage',
# 	y_label='Energy (kWh)',
# 	series_map=[
# 		('Solar Energy (kWh)', 'solar_energy_kwh'),
# 		('Power Usage (kWh)', 'power_usage_kwh'),
# 	],
# )

# Convert per-interval energy (kWh per 5 min) to average power (kW) for PyPSA dispatch.
df['solar_power_kw'] = df['solar_energy_kwh'] / DT_HOURS
df['load_power_kw'] = df['power_usage_kwh'] / DT_HOURS

# Price in EUR/kWh; grid import cost includes network tariff + VAT
df['epex_eur_kwh'] = df['epex_price_eur_mwh'] / 1000
df['import_cost_eur_kwh'] = (df['epex_eur_kwh'] + FIXED_NETWORK_TARIFF) * (1 + VAT)

peak_solar_kw = df['solar_power_kw'].max()
if peak_solar_kw == 0:
    raise ValueError("Solar production is all-zero — check source data.")

solar_pu = df['solar_power_kw'] / peak_solar_kw  # normalised 0–1


# --- Build PyPSA network ---
n = pypsa.Network()
n.set_snapshots(df.index)
n.snapshot_weightings.loc[:, 'objective'] = DT_HOURS
n.snapshot_weightings.loc[:, 'stores'] = DT_HOURS
n.snapshot_weightings.loc[:, 'generators'] = DT_HOURS

n.add("Bus", "home")

n.add(
    "Generator",
    "solar",
    bus="home",
    p_nom=peak_solar_kw,
    p_max_pu=solar_pu,
    marginal_cost=0.0,
)

n.add(
    "Load",
    "home_load",
    bus="home",
    p_set=df['load_power_kw'],
)

n.add(
    "StorageUnit",
    "battery",
    bus="home",
    p_nom=BATTERY_POWER_KW,
    max_hours=BATTERY_CAPACITY_KWH / BATTERY_POWER_KW,
    efficiency_store=BATTERY_EFF_SIDE,
    efficiency_dispatch=BATTERY_EFF_SIDE,
    cyclic_state_of_charge=True,
    marginal_cost=0.0,
)

# Grid import: spot price + network tariff + 21% VAT
n.add(
    "Generator",
    "grid_import",
    bus="home",
    p_nom=GRID_MAX_KW,
    p_min_pu=0.0,
    marginal_cost=df['import_cost_eur_kwh'],
)

# Grid export (solar only — enforced by custom constraint): revenue at spot price
n.add(
    "Generator",
    "grid_export",
    bus="home",
    p_nom=peak_solar_kw,
    p_min_pu=0.0,
    marginal_cost=-df['epex_eur_kwh'],  # negative = revenue
    sign=-1,  # withdraws power from the bus (acts as a sink)
)


def battery_no_export_constraint(n, snapshots):
    """Battery may not export to the grid; only solar can."""
    m = n.model
    gen_p = m["Generator-p"]
    export_p = gen_p.sel(name="grid_export")
    solar_p = gen_p.sel(name="solar")
    m.add_constraints(export_p - solar_p <= 0, name="export_le_solar")


status, condition = n.optimize(
    extra_functionality=battery_no_export_constraint,
    solver_name="highs",
    include_objective_constant=False,
)
print(f"\nOptimization status: {status} — {condition}")

if status != "ok":
    raise RuntimeError(f"Solver did not find an optimal solution: {status} — {condition}")


# --- Results ---
solar_p   = n.generators_t.p["solar"]
import_p  = n.generators_t.p["grid_import"]
export_p  = n.generators_t.p["grid_export"]
battery_p = n.storage_units_t.p["battery"]       # positive = discharge, negative = charge
soc       = n.storage_units_t.state_of_charge["battery"]

import_energy_kwh = import_p * DT_HOURS
export_energy_kwh = export_p * DT_HOURS
total_import_kwh  = import_energy_kwh.sum()
total_export_kwh  = export_energy_kwh.sum()
total_import_cost = (import_energy_kwh * df['import_cost_eur_kwh']).sum()
total_export_rev  = (export_energy_kwh * df['epex_eur_kwh']).sum()
net_cost          = total_import_cost - total_export_rev

# Baseline A: measured grid flows from meter data (billing ground truth)
base_measured_import_p = df['delta_power_import_kwh'].clip(lower=0)
base_measured_export_p = df['delta_power_export_kwh'].clip(lower=0)
base_measured_cost = (
    (base_measured_import_p * df['import_cost_eur_kwh']).sum()
    - (base_measured_export_p * df['epex_eur_kwh']).sum()
)

# Baseline B: model-consistent no-battery baseline from 5-minute net flows
base_model_import_p = (df['power_usage_kwh'] - df['solar_energy_kwh']).clip(lower=0)
base_model_export_p = (df['solar_energy_kwh'] - df['power_usage_kwh']).clip(lower=0)
base_model_cost = (
    (base_model_import_p * df['import_cost_eur_kwh']).sum()
    - (base_model_export_p * df['epex_eur_kwh']).sum()
)

print(f"\n{'='*50}")
print(f"  Grid import : {total_import_kwh:>10.1f} kWh")
print(f"  Grid export : {total_export_kwh:>10.1f} kWh")
print(f"  Import cost : €{total_import_cost:>9.2f}")
print(f"  Export rev  : €{total_export_rev:>9.2f}")
print(f"  Net cost    : €{net_cost:>9.2f}")
print(f"  Baseline (measured) : €{base_measured_cost:>9.2f}")
print(f"  Savings vs measured : €{base_measured_cost - net_cost:>9.2f}")
print(f"  Baseline (model)    : €{base_model_cost:>9.2f}")
print(f"  Savings vs model    : €{base_model_cost - net_cost:>9.2f}")
print(f"{'='*50}\n")


# --- Plot ---
fig, axes = plt.subplots(4, 1, figsize=(14, 12), sharex=True)

ax1, ax2, ax3, ax4 = axes

ax1.plot(df.index, solar_p, label='Solar production (kW)', color='gold')
ax1.plot(df.index, n.loads_t.p_set["home_load"], label='Home load (kW)', color='steelblue')
ax1.plot(df.index, battery_p.clip(lower=0), label='Battery discharge (kW)', color='mediumpurple')
ax1.set_ylabel('kW')
ax1.set_title('Solar production vs Home load')
ax1.legend(loc='upper right')
ax1.grid(alpha=0.3)

ax2.fill_between(df.index, import_p, 0, where=import_p > 0, label='Grid import (kW)', color='tomato', alpha=0.7)
ax2.fill_between(df.index, -export_p, 0, where=export_p > 0, label='Grid export (kW)', color='mediumseagreen', alpha=0.7)
ax2.set_ylabel('kW')
ax2.set_title('Grid import / export')
ax2.legend(loc='upper right')
ax2.grid(alpha=0.3)

ax3.fill_between(df.index, soc, 0, color='mediumpurple', alpha=0.7, label='Battery SoC (kWh)')
ax3.axhline(BATTERY_CAPACITY_KWH, color='mediumpurple', linestyle='--', linewidth=0.8, alpha=0.5)
ax3.set_ylabel('kWh')
ax3.set_title('Battery State of Charge')
ax3.set_ylim(0, BATTERY_CAPACITY_KWH * 1.1)
ax3.legend(loc='upper right')
ax3.grid(alpha=0.3)

ax4.plot(df.index, df['epex_price_eur_mwh'], color='darkorange', linewidth=0.8, label='EPEX price (€/MWh)')
ax4.set_ylabel('€/MWh')
ax4.set_title('EPEX spot price')
ax4.legend(loc='upper right')
ax4.grid(alpha=0.3)

fig.autofmt_xdate()
plt.tight_layout()
plt.show()
