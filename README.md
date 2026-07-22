# Energy Analytics Hub

Lightweight energy data collector for Raspberry Pi Zero 2W.

The app fetches HomeWizard P1 readings and stores them in a local SQLite database.
It is designed to run every 15 minutes with systemd timer units.

## Stack

- Python 3.12
- uv (dependency management + virtual environment)
- SQLite (local file database)
- Pydantic (data validation)
- pytest + pytest-cov
- Ruff (lint + formatting)

## Current Status

Implemented:

- Collector foundation and HomeWizard P1 collector with retry + circuit breaker
- SQLite schema initialization with versioning
- Raw readings table and hourly aggregate table
- Query functions for latest, hourly, and daily summaries
- systemd service and timer unit files
- Full automated test suite (mocked, no real meter required)

## Project Layout

```text
src/
	collectors/
		base.py
		homewizard.py
	db/
		init.py
		queries.py
	models/
		readings.py
	config.py
	main.py
tests/
deploy/
	energy-analytics.service
	energy-analytics.timer
```

## Quick Start (Local)

### 1. Install dependencies

```bash
uv sync
```

### 2. Run tests

This works without a HomeWizard meter because all external calls are mocked.

```bash
uv run pytest
```

With extra detail:

```bash
uv run pytest -v --cov=src --cov-report=term-missing
```

### 3. Lint and format

```bash
uv run ruff check .
uv run ruff format .
```

## Configuration

The app reads configuration from environment variables.

For local development, `.env.local` in the project root is auto-loaded.
Process environment variables still override values from `.env.local`.

Required:

- HOMEWIZARD_HOST
- HOMEWIZARD_DEVICE_ID

Optional:

- DB_PATH (default: ~/energy.db)
- HOMEWIZARD_TIMEOUT (default: 5)

Example:

```bash
export HOMEWIZARD_HOST=192.168.1.50
export HOMEWIZARD_DEVICE_ID=p1-meter-01
export DB_PATH=$HOME/energy.db
export HOMEWIZARD_TIMEOUT=5
```

Or edit `.env.local` and run directly:

```bash
uv run python -m src.main
```

## Run One Collection Manually

```bash
uv run python -m src.main
```

Expected behavior:

1. Database is initialized (idempotent).
2. One reading is fetched from HomeWizard.
3. Reading is inserted into energy_readings.
4. Hourly aggregate is inserted/updated in energy_hourly.

If you do not have a P1 meter yet, this command will fail on missing env vars or network call.
That is expected. Use the test suite to validate functionality before hardware arrives.

## Database Notes

- SQLite database file is local (default: ~/energy.db)
- WAL mode is enabled
- Schema version is tracked with PRAGMA user_version
- Raw readings older than 7 days are auto-cleaned by trigger
- Hourly aggregates are kept for long-term insights

## Inspect Data Locally

```bash
sqlite3 ~/energy.db ".tables"
sqlite3 ~/energy.db "SELECT * FROM energy_readings ORDER BY timestamp DESC LIMIT 10;"
sqlite3 ~/energy.db "SELECT * FROM energy_hourly ORDER BY hour_start DESC LIMIT 10;"
```

## Deploy on Raspberry Pi (systemd)

Copy units:

```bash
sudo cp deploy/energy-analytics.service /etc/systemd/system/
sudo cp deploy/energy-analytics.timer /etc/systemd/system/
sudo systemctl daemon-reload
```

Enable timer:

```bash
sudo systemctl enable --now energy-analytics.timer
```

Check status and logs:

```bash
systemctl status energy-analytics.timer
systemctl status energy-analytics.service
journalctl -u energy-analytics.service -f
```

Important:

- Update environment values in the service file before enabling.
- The provided service uses user/path values that may need to be changed for your Pi setup.

## Copy Data From RPi To PC (No API Needed)

Safe snapshot on Pi:

```bash
sqlite3 /home/pi/energy.db ".backup /home/pi/energy_export.db"
```

Copy to PC:

```bash
scp pi@<rpi-ip>:/home/pi/energy_export.db .
```

## Troubleshooting

### uv run python -m src.main exits with code 1

Most common causes:

- Missing HOMEWIZARD_HOST
- Missing HOMEWIZARD_DEVICE_ID
- HomeWizard device not reachable

### Tests pass, but no real data yet

This is normal without a configured P1 meter. Tests validate app logic with mocks.

## Next Steps

1. Add a synthetic data collector mode for development without hardware.
2. Add FastAPI read endpoints for dashboard integration.
3. Add APSystems collector using the same collector interface.