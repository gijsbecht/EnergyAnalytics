import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    # HomeWizard P1 meter local IP address
    homewizard_host: str

    # Unique identifier for the P1 device (e.g. serial number or hostname)
    homewizard_device_id: str

    # Path to the SQLite database file
    db_path: Path

    # HTTP request timeout for the HomeWizard API
    homewizard_timeout_s: float = 5.0


@dataclass(frozen=True)
class APSystemsConfig:
    # APSystems EMA API credentials
    app_id: str
    app_secret: str

    # System ID and ECU ID from the APSystems EMA portal
    sid: str
    ecu_id: str

    # Path to the SQLite database file
    db_path: Path

    # HTTP request timeout
    timeout_s: float = 10.0


def load_config(env_file: Path | None = None) -> Config:
    """Load configuration from a local env file and environment variables.

    Required environment variables:
        HOMEWIZARD_HOST        Local IP or hostname of the P1 meter
        HOMEWIZARD_DEVICE_ID   Unique identifier for this device

    Optional environment variables:
        DB_PATH                Path to the SQLite database (default: ~/energy.db)
        HOMEWIZARD_TIMEOUT     HTTP timeout in seconds (default: 5)

    Local file behavior:
        If env_file is not provided, .env.local in the project root is read
        automatically (when present). Variables already set in the process
        environment always take precedence.
    """
    if env_file is None:
        env_file = Path(__file__).resolve().parent.parent / ".env.local"

    # Do not override existing process environment values.
    load_dotenv(dotenv_path=env_file, override=False)

    host = os.environ.get("HOMEWIZARD_HOST")
    if not host:
        raise RuntimeError("Missing required environment variable: HOMEWIZARD_HOST")

    device_id = os.environ.get("HOMEWIZARD_DEVICE_ID")
    if not device_id:
        raise RuntimeError("Missing required environment variable: HOMEWIZARD_DEVICE_ID")

    db_path = Path(os.environ.get("DB_PATH", Path.home() / "energy.db"))

    timeout = float(os.environ.get("HOMEWIZARD_TIMEOUT", "5"))

    return Config(
        homewizard_host=host,
        homewizard_device_id=device_id,
        db_path=db_path,
        homewizard_timeout_s=timeout,
    )


def load_apsystems_config(env_file: Path | None = None) -> APSystemsConfig:
    """Load APSystems configuration from a local env file and environment variables.

    Required environment variables:
        APSYSTEMS_APP_ID       API application ID from APSystems EMA portal
        APSYSTEMS_APP_SECRET   API application secret
        APSYSTEMS_SID          System ID
        APSYSTEMS_ECU_ID       ECU ID

    Optional environment variables:
        DB_PATH                Path to the SQLite database (default: ~/energy.db)
        APSYSTEMS_TIMEOUT      HTTP timeout in seconds (default: 10)
    """
    if env_file is None:
        env_file = Path(__file__).resolve().parent.parent / ".env.local"

    load_dotenv(dotenv_path=env_file, override=False)

    app_id = os.environ.get("APSYSTEMS_APP_ID")
    if not app_id:
        raise RuntimeError("Missing required environment variable: APSYSTEMS_APP_ID")

    app_secret = os.environ.get("APSYSTEMS_APP_SECRET")
    if not app_secret:
        raise RuntimeError("Missing required environment variable: APSYSTEMS_APP_SECRET")

    sid = os.environ.get("APSYSTEMS_SID")
    if not sid:
        raise RuntimeError("Missing required environment variable: APSYSTEMS_SID")

    ecu_id = os.environ.get("APSYSTEMS_ECU_ID")
    if not ecu_id:
        raise RuntimeError("Missing required environment variable: APSYSTEMS_ECU_ID")

    db_path = Path(os.environ.get("DB_PATH", Path.home() / "energy.db"))

    timeout = float(os.environ.get("APSYSTEMS_TIMEOUT", "10"))

    return APSystemsConfig(
        app_id=app_id,
        app_secret=app_secret,
        sid=sid,
        ecu_id=ecu_id,
        db_path=db_path,
        timeout_s=timeout,
    )
