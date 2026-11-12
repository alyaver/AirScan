"""Application configuration for the local AirScan backend."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_SERIAL_BAUD_RATE = 115200


def _repository_root() -> Path:
    """Return the repository root from this module's fixed package location."""

    return Path(__file__).resolve().parents[2]


def _read_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise ValueError("AIRSCAN_PORT must be an integer.") from error

    if not 1 <= port <= 65535:
        raise ValueError("AIRSCAN_PORT must be between 1 and 65535.")

    return port


def _read_baud_rate(value: str) -> int:
    try:
        baud_rate = int(value)
    except ValueError as error:
        raise ValueError("AIRSCAN_SERIAL_BAUD_RATE must be an integer.") from error

    if baud_rate <= 0:
        raise ValueError("AIRSCAN_SERIAL_BAUD_RATE must be greater than zero.")

    return baud_rate


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from local environment variables."""

    host: str
    port: int
    serial_baud_rate: int
    serial_port: str | None
    data_dir: Path


def get_settings() -> Settings:
    """Load and validate backend settings from the process environment."""

    host = os.getenv("AIRSCAN_HOST", DEFAULT_HOST).strip()
    if not host:
        raise ValueError("AIRSCAN_HOST must not be empty.")

    data_dir_value = os.getenv("AIRSCAN_DATA_DIR")
    data_dir = (
        Path(data_dir_value).expanduser()
        if data_dir_value
        else _repository_root() / "data"
    )
    serial_port = os.getenv("AIRSCAN_SERIAL_PORT", "").strip() or None

    return Settings(
        host=host,
        port=_read_port(os.getenv("AIRSCAN_PORT", str(DEFAULT_PORT))),
        serial_baud_rate=_read_baud_rate(
            os.getenv("AIRSCAN_SERIAL_BAUD_RATE", str(DEFAULT_SERIAL_BAUD_RATE))
        ),
        serial_port=serial_port,
        data_dir=data_dir,
    )