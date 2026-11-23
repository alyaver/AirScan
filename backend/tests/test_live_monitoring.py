from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.serial.protocol import ProtocolParser
from app.serial.state import ConnectionStateTracker


def test_live_scan_updates_do_not_create_or_write_the_configured_data_directory(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "live-monitoring-data"
    tracker = ConnectionStateTracker()
    parser = ProtocolParser(message_handler=tracker.record_message)
    application = create_app(
        Settings(
            host="127.0.0.1",
            port=8000,
            serial_baud_rate=115200,
            serial_port=None,
            data_dir=data_dir,
        ),
        connection_state=tracker,
        protocol_parser=parser,
    )

    tracker.record_lifecycle("connected", "COM7")
    parser.parse_line(
        '{"protocol_version":1,"message_type":"scan_result","scan_id":1,'
        '"device_timestamp_ms":1,"networks":[{"ssid":"AirScan",'
        '"bssid":"aa:bb:cc:dd:ee:ff","rssi_dbm":-50,"channel":6,'
        '"encryption":"Encrypted"}]}'
    )
    response = TestClient(application).get("/api/live")

    assert response.status_code == 200
    assert response.json()["scan_count"] == 1
    assert response.json()["networks"][0]["bssid"] == "AA:BB:CC:DD:EE:FF"
    assert data_dir.exists() is False