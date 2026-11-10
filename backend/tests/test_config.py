from pathlib import Path

import pytest

from app.config import DEFAULT_HOST, DEFAULT_PORT, DEFAULT_SERIAL_BAUD_RATE, get_settings


def test_get_settings_uses_local_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in (
        "AIRSCAN_HOST",
        "AIRSCAN_PORT",
        "AIRSCAN_SERIAL_BAUD_RATE",
        "AIRSCAN_DATA_DIR",
    ):
        monkeypatch.delenv(variable, raising=False)

    settings = get_settings()

    assert settings.host == DEFAULT_HOST
    assert settings.port == DEFAULT_PORT
    assert settings.serial_baud_rate == DEFAULT_SERIAL_BAUD_RATE
    assert settings.data_dir.name == "data"
    assert settings.data_dir.parent.name == "AirScan"


def test_get_settings_reads_valid_environment_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("AIRSCAN_HOST", "localhost")
    monkeypatch.setenv("AIRSCAN_PORT", "8123")
    monkeypatch.setenv("AIRSCAN_SERIAL_BAUD_RATE", "230400")
    monkeypatch.setenv("AIRSCAN_DATA_DIR", str(tmp_path / "airscan-data"))

    settings = get_settings()

    assert settings.host == "localhost"
    assert settings.port == 8123
    assert settings.serial_baud_rate == 230400
    assert settings.data_dir == tmp_path / "airscan-data"


@pytest.mark.parametrize("port", ["not-a-port", "0", "65536"])
def test_get_settings_rejects_invalid_port(
    monkeypatch: pytest.MonkeyPatch, port: str
) -> None:
    monkeypatch.setenv("AIRSCAN_PORT", port)

    with pytest.raises(ValueError, match="AIRSCAN_PORT"):
        get_settings()