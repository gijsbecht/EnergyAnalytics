# Energy Analytics Hub

Lightweight energy data collector for Raspberry Pi Zero 2W.

The project currently collects three data layers into SQLite:

- HomeWizard P1 meter telemetry (high-frequency point readings)
- APSystems 5-minute solar energy (daily batch for previous day)
- EPEX NL day-ahead hourly spot prices (daily batch for previous day)

## Stack

- Python 3.12
- uv (dependency management + virtual environment)
- SQLite (local file database)
- Pydantic (data validation)
- requests (HTTP clients)
- pytest + pytest-cov
- Ruff (lint + formatting)

## Current Status

Implemented:

- Collector foundation and HomeWizard P1 collector with retry + circuit breaker
- APSystems collector with HMAC-signed API requests
- EPEX collector for NL day-ahead spot pricing
- SQLite schema initialization with versioning
- `energy_readings` raw P1 table + `energy_hourly` view
- `apsystems_readings` 5-minute solar table
- `epex_spot_prices` hourly pricing table
- `energy_combined_hourly` view joining P1 + APSystems + EPEX by hour
- `energy_combined_5min` view joining P1 + APSystems + EPEX on 5-minute buckets
- systemd units for 5-minute P1 collection and daily batch collection
- Full automated test suite with mocked external APIs

## Project Layout

```text
src/
	collectors/
		base.py
		homewizard.py
		apsystems.py
		epex.py
	db/
		init.py
		queries.py
	models/
		readings.py
	config.py
	main.py
	main_daily.py
tests/
deploy/
	energy-analytics.service
	energy-analytics.timer
	daily-collection.service
	daily-collection.timer
```

## Quick Start (Local)

### 1. Install dependencies

```bash
uv sync
```

### 2. Run tests

This works without real devices/API keys because external calls are mocked.

```bash
uv run pytest
```

### 3. Lint and format

```bash
uv run ruff check .
uv run ruff format .
```

## Configuration

The app loads `.env.local` automatically (when present), without overriding
already-set process environment variables.

### P1 collector (`src.main`)

Required:

- `HOMEWIZARD_HOST`
- `HOMEWIZARD_DEVICE_ID`

Optional:

- `DB_PATH` (default: `~/energy.db`)
- `HOMEWIZARD_TIMEOUT` (default: `5`)

### Daily APSystems + EPEX collector (`src.main_daily`)

Required:

- `APSYSTEMS_APP_ID`
- `APSYSTEMS_APP_SECRET`
- `APSYSTEMS_SID`
- `APSYSTEMS_ECU_ID`
- `PARSE_API_KEY`

Optional:

- `DB_PATH` (default: `~/energy.db`)
- `APSYSTEMS_TIMEOUT` (default: `10`)
- `EPEX_TIMEOUT` (default: `10`)

## Run Manually

P1 single run:

```bash
uv run python -m src.main
```

Daily APSystems + EPEX run:

```bash
uv run python -m src.main_daily
```

## Timezone Notes (Important)

EPEX responses include both `datetime` and `timestamp_ms` fields. The
implementation uses `timestamp_ms` as source of truth to avoid timezone
ambiguity in the string field.

Example for NL/CEST delivery day:

- `2026-07-27T22:00:00` UTC corresponds to local `2026-07-28 00:00`

Using epoch timestamps ensures correct joins across both hourly and 5-minute data layers.

## Database Notes

- SQLite database file is local (default: `~/energy.db`)
- WAL mode is enabled
- Schema version is tracked with `PRAGMA user_version`
- `init_db()` is idempotent and safe to run on each invocation

Main structures:

- `energy_readings` (raw P1 data)
- `energy_hourly` (closest-sample-per-hour P1 view)
- `apsystems_readings` (5-minute solar kWh)
- `epex_spot_prices` (hourly EUR/MWh)
- `energy_combined_hourly` (joined hourly view)
- `energy_combined_5min` (joined 5-minute view)

## Inspect Data Locally

```bash
sqlite3 ~/energy.db ".tables"
sqlite3 ~/energy.db "SELECT * FROM energy_hourly ORDER BY timestamp DESC LIMIT 10;"
sqlite3 ~/energy.db "SELECT * FROM apsystems_readings ORDER BY timestamp DESC LIMIT 10;"
sqlite3 ~/energy.db "SELECT * FROM epex_spot_prices ORDER BY timestamp DESC LIMIT 10;"
sqlite3 ~/energy.db "SELECT * FROM energy_combined_hourly ORDER BY hour_ts DESC LIMIT 24;"
sqlite3 ~/energy.db "SELECT * FROM energy_combined_5min ORDER BY five_min_ts DESC LIMIT 24;"
```

## Deploy on Raspberry Pi (systemd)

### 5-minute P1 collection

```bash
sudo cp deploy/energy-analytics.service /etc/systemd/system/
sudo cp deploy/energy-analytics.timer /etc/systemd/system/
```

### Daily APSystems + EPEX collection

```bash
sudo cp deploy/daily-collection.service /etc/systemd/system/
sudo cp deploy/daily-collection.timer /etc/systemd/system/
```

Reload and enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now energy-analytics.timer
sudo systemctl enable --now daily-collection.timer
```

Check status/logs:

```bash
systemctl status energy-analytics.timer
systemctl status daily-collection.timer
journalctl -u energy-analytics.service -f
journalctl -u daily-collection.service -f
```

Important:

- Update environment values in both service files before enabling.
- Adjust `User`, `WorkingDirectory`, and virtualenv path for your Pi setup.

## Troubleshooting

### `uv run python -m src.main` exits with code 1

Most common causes:

- Missing `HOMEWIZARD_HOST`
- Missing `HOMEWIZARD_DEVICE_ID`
- HomeWizard device unreachable

### `uv run python -m src.main_daily` exits with code 1

Most common causes:

- Missing one of `APSYSTEMS_*` variables
- Missing `PARSE_API_KEY`
- APSystems/EPEX API unavailable or credentials invalid

### Tests pass, but no real data yet

Normal when hardware/API keys are not configured. Tests validate logic with mocks.