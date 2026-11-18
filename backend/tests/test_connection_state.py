from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.serial.manager import SerialPortManager
from app.serial.protocol import ProtocolParser
from app.serial.state import ConnectionState, ConnectionStateTracker


def test_state_tracker_transitions_from_lifecycle_and_protocol_messages() -> None:
    tracker = ConnectionStateTracker()
    parser = ProtocolParser(message_handler=tracker.record_message)

    tracker.record_lifecycle("connecting", "COM7")
    assert tracker.details().state is ConnectionState.CONNECTING

    tracker.record_lifecycle("connected", "COM7")
    parser.parse_line(
        '{"protocol_version":1,"message_type":"device_ready",'
        '"device_id":"esp32-ABC","firmware_version":"0.1.0",'
        '"device_timestamp_ms":1}'
    )
    assert tracker.details().state is ConnectionState.CONNECTED_IDLE
    assert tracker.details().device_id == "esp32-ABC"

    parser.parse_line(
        '{"protocol_version":1,"message_type":"heartbeat",'
        '"device_timestamp_ms":2,"scan_in_progress":true}'
    )
    assert tracker.details().state is ConnectionState.CONNECTED_SCANNING

    parser.parse_line(
        '{"protocol_version":1,"message_type":"scan_result","scan_id":1,'
        '"device_timestamp_ms":3,"networks":[]}'
    )
    assert tracker.details().state is ConnectionState.CONNECTED_IDLE
    assert tracker.details().last_scan_at is not None
    assert tracker.latest_scan().scan_id == 1
    assert tracker.latest_scan().networks == ()
    assert tracker.live_scan().scan_count == 1


def test_state_tracker_exposes_device_and_reader_errors_without_claiming_disconnect() -> None:
    tracker = ConnectionStateTracker()
    parser = ProtocolParser(message_handler=tracker.record_message)

    tracker.record_lifecycle("connected", "COM7")
    parser.parse_line(
        '{"protocol_version":1,"message_type":"device_error",'
        '"device_timestamp_ms":4,"error_code":"wifi_failed",'
        '"message":"Wi-Fi initialization failed."}'
    )

    assert tracker.details().state is ConnectionState.ERROR
    assert tracker.details().last_error == "wifi_failed: Wi-Fi initialization failed."

    tracker.record_lifecycle("error", "COM7", OSError("device disconnected"))
    assert tracker.details().state is ConnectionState.ERROR
    assert tracker.details().last_error == "device disconnected"


def test_state_tracker_replaces_networks_with_terminal_scan_error() -> None:
    tracker = ConnectionStateTracker()
    parser = ProtocolParser(message_handler=tracker.record_message)

    parser.parse_line(
        '{"protocol_version":1,"message_type":"scan_result","scan_id":1,'
        '"device_timestamp_ms":3,"networks":[{"ssid":"AirScan",'
        '"bssid":"aa:bb:cc:dd:ee:ff","rssi_dbm":-50,"channel":6,'
        '"encryption":"Encrypted"}]}'
    )
    parser.parse_line(
        '{"protocol_version":1,"message_type":"scan_error","scan_id":2,'
        '"device_timestamp_ms":4,"error_code":"wifi_scan_failed",'
        '"message":"scan failed"}'
    )

    latest_scan = tracker.latest_scan()
    assert latest_scan.scan_id == 2
    assert latest_scan.networks == ()
    assert latest_scan.error_code == "wifi_scan_failed"
    assert latest_scan.error_message == "scan failed"
    assert tracker.live_scan().scan_count == 2


def test_state_tracker_clears_device_metadata_after_explicit_disconnect() -> None:
    tracker = ConnectionStateTracker()
    parser = ProtocolParser(message_handler=tracker.record_message)
    tracker.record_lifecycle("connected", "COM7")
    parser.parse_line(
        '{"protocol_version":1,"message_type":"device_ready",'
        '"device_id":"esp32-ABC","firmware_version":"0.1.0",'
        '"device_timestamp_ms":1}'
    )

    tracker.record_lifecycle("disconnected", "COM7")

    assert tracker.details().state is ConnectionState.DISCONNECTED
    assert tracker.details().selected_port == "COM7"
    assert tracker.details().device_id is None
    assert tracker.details().last_message_at is None
    assert tracker.live_scan().scan_count == 0
    assert tracker.live_scan().networks == ()


def test_serial_state_endpoint_returns_the_tracker_snapshot() -> None:
    tracker = ConnectionStateTracker()
    app = create_app(
        Settings(
            host="127.0.0.1",
            port=8000,
            serial_baud_rate=115200,
            serial_port=None,
            data_dir=Path("data"),
        ),
        connection_state=tracker,
    )
    tracker.record_lifecycle("reconnecting", "COM7")

    response = TestClient(app).get("/api/serial/state")

    assert response.status_code == 200
    assert response.json() == {
        "state": "RECONNECTING",
        "selected_port": "COM7",
        "device_id": None,
        "firmware_version": None,
        "last_message_at": None,
        "last_scan_at": None,
        "last_error": None,
    }


def test_device_status_and_latest_scan_endpoints_expose_normalized_state() -> None:
    tracker = ConnectionStateTracker()
    parser = ProtocolParser(message_handler=tracker.record_message)
    manager = SerialPortManager(baud_rate=115200)
    app = create_app(
        Settings(
            host="127.0.0.1",
            port=8000,
            serial_baud_rate=115200,
            serial_port=None,
            data_dir=Path("data"),
        ),
        serial_manager=manager,
        protocol_parser=parser,
        connection_state=tracker,
    )
    tracker.record_lifecycle("connected", "COM7")
    parser.parse_line(
        '{"protocol_version":1,"message_type":"device_ready",'
        '"device_id":"esp32-ABC","firmware_version":"0.1.0",'
        '"device_timestamp_ms":1}'
    )
    parser.parse_line(
        '{"protocol_version":1,"message_type":"scan_result","scan_id":1,'
        '"device_timestamp_ms":2,"networks":[{"ssid":"AirScan",'
        '"bssid":"aa:bb:cc:dd:ee:ff","rssi_dbm":-50,"channel":6,'
        '"encryption":"Encrypted"}]}'
    )
    client = TestClient(app)

    status_response = client.get("/api/device/status")
    latest_scan_response = client.get("/api/scans/latest")

    assert status_response.status_code == 200
    assert status_response.json()["state"] == "CONNECTED_IDLE"
    assert status_response.json()["device_id"] == "esp32-ABC"
    assert status_response.json()["parser"]["accepted_messages"] == 2
    assert status_response.json()["reader"] is None
    assert latest_scan_response.status_code == 200
    assert latest_scan_response.json()["scan_id"] == 1
    assert latest_scan_response.json()["networks"] == [
        {
            "ssid": "AirScan",
            "bssid": "AA:BB:CC:DD:EE:FF",
            "rssi_dbm": -50,
            "channel": 6,
            "encryption": "Encrypted",
        }
    ]


def test_live_endpoint_explicitly_represents_disconnected_and_scanning_states() -> None:
    tracker = ConnectionStateTracker()
    parser = ProtocolParser(message_handler=tracker.record_message)
    app = create_app(
        Settings(
            host="127.0.0.1",
            port=8000,
            serial_baud_rate=115200,
            serial_port=None,
            data_dir=Path("data"),
        ),
        protocol_parser=parser,
        connection_state=tracker,
    )
    client = TestClient(app)

    disconnected_response = client.get("/api/live")

    tracker.record_lifecycle("connected", "COM7")
    parser.parse_line(
        '{"protocol_version":1,"message_type":"heartbeat",'
        '"device_timestamp_ms":1,"scan_in_progress":true}'
    )
    scanning_response = client.get("/api/live")

    assert disconnected_response.status_code == 200
    assert disconnected_response.json() == {
        "connection_state": "DISCONNECTED",
        "last_scan_at": None,
        "networks": [],
        "scan_count": 0,
        "error": None,
    }
    assert scanning_response.status_code == 200
    assert scanning_response.json() == {
        "connection_state": "CONNECTED_SCANNING",
        "last_scan_at": None,
        "networks": [],
        "scan_count": 0,
        "error": None,
    }


def test_live_endpoint_returns_latest_scan_count_and_terminal_error() -> None:
    tracker = ConnectionStateTracker()
    parser = ProtocolParser(message_handler=tracker.record_message)
    app = create_app(
        Settings(
            host="127.0.0.1",
            port=8000,
            serial_baud_rate=115200,
            serial_port=None,
            data_dir=Path("data"),
        ),
        protocol_parser=parser,
        connection_state=tracker,
    )
    tracker.record_lifecycle("connected", "COM7")
    parser.parse_line(
        '{"protocol_version":1,"message_type":"scan_result","scan_id":1,'
        '"device_timestamp_ms":1,"networks":[{"ssid":"AirScan",'
        '"bssid":"aa:bb:cc:dd:ee:ff","rssi_dbm":-50,"channel":6,'
        '"encryption":"Encrypted"}]}'
    )
    client = TestClient(app)

    successful_scan = client.get("/api/live")

    parser.parse_line(
        '{"protocol_version":1,"message_type":"scan_error","scan_id":2,'
        '"device_timestamp_ms":2,"error_code":"wifi_scan_failed",'
        '"message":"scan failed"}'
    )
    failed_scan = client.get("/api/live")

    assert successful_scan.status_code == 200
    assert successful_scan.json()["connection_state"] == "CONNECTED_IDLE"
    assert successful_scan.json()["scan_count"] == 1
    assert successful_scan.json()["error"] is None
    assert successful_scan.json()["networks"][0]["bssid"] == "AA:BB:CC:DD:EE:FF"
    assert successful_scan.json()["last_scan_at"] is not None
    assert failed_scan.status_code == 200
    assert failed_scan.json() == {
        "connection_state": "CONNECTED_IDLE",
        "last_scan_at": failed_scan.json()["last_scan_at"],
        "networks": [],
        "scan_count": 2,
        "error": "wifi_scan_failed: scan failed",
    }
    assert failed_scan.json()["last_scan_at"] is not None