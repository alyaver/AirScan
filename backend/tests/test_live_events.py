from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.live.events import LiveEventBroker
from app.main import create_app
from app.serial.protocol import ProtocolParser
from app.serial.state import ConnectionStateTracker


def build_app() -> tuple[object, ConnectionStateTracker, ProtocolParser, LiveEventBroker]:
    tracker = ConnectionStateTracker()
    parser = ProtocolParser(message_handler=tracker.record_message)
    broker = LiveEventBroker(queue_size=1)
    application = create_app(
        Settings(
            host="127.0.0.1",
            port=8000,
            serial_baud_rate=115200,
            serial_port=None,
            data_dir=Path("data"),
        ),
        protocol_parser=parser,
        connection_state=tracker,
        live_event_broker=broker,
    )
    return application, tracker, parser, broker


def test_websocket_sends_an_initial_disconnected_snapshot() -> None:
    application, _, _, _ = build_app()

    with TestClient(application).websocket_connect("/api/live") as websocket:
        event = websocket.receive_json()

    assert event == {
        "event_type": "snapshot",
        "connection": {
            "state": "DISCONNECTED",
            "selected_port": None,
            "device_id": None,
            "firmware_version": None,
            "last_message_at": None,
            "last_scan_at": None,
            "last_error": None,
        },
        "live": {
            "connection_state": "DISCONNECTED",
            "last_scan_at": None,
            "networks": [],
            "scan_count": 0,
            "error": None,
        },
        "latest_scan": {
            "scan_id": None,
            "completed_at": None,
            "networks": [],
            "error_code": None,
            "error_message": None,
        },
    }


def test_websocket_broadcasts_scan_updates_to_multiple_clients() -> None:
    application, tracker, parser, _ = build_app()
    client = TestClient(application)

    with client.websocket_connect("/api/live") as first, client.websocket_connect(
        "/api/live"
    ) as second:
        assert first.receive_json()["event_type"] == "snapshot"
        assert second.receive_json()["event_type"] == "snapshot"
        tracker.record_lifecycle("connected", "COM7")
        assert first.receive_json()["event_type"] == "connection_state"
        assert second.receive_json()["event_type"] == "connection_state"

        parser.parse_line(
            '{"protocol_version":1,"message_type":"scan_result","scan_id":1,'
            '"device_timestamp_ms":1,"networks":[{"ssid":"AirScan",'
            '"bssid":"aa:bb:cc:dd:ee:ff","rssi_dbm":-50,"channel":6,'
            '"encryption":"Encrypted"}]}'
        )

        first_update = first.receive_json()
        second_update = second.receive_json()

    for event in (first_update, second_update):
        assert event["event_type"] == "scan_update"
        assert event["live"]["scan_count"] == 1
        assert event["live"]["networks"][0]["bssid"] == "AA:BB:CC:DD:EE:FF"
        assert event["latest_scan"]["scan_id"] == 1


def test_websocket_publishes_connection_state_changes() -> None:
    application, tracker, _, _ = build_app()

    with TestClient(application).websocket_connect("/api/live") as websocket:
        websocket.receive_json()
        tracker.record_lifecycle("reconnecting", "COM7")
        event = websocket.receive_json()

    assert event["event_type"] == "connection_state"
    assert event["connection"]["state"] == "RECONNECTING"
    assert event["live"]["connection_state"] == "RECONNECTING"


def test_broker_replaces_stale_events_for_a_slow_client_without_blocking() -> None:
    broker = LiveEventBroker(queue_size=1)
    slow_client = broker.subscribe()
    fast_client = broker.subscribe()

    broker.publish({"sequence": 1})
    assert fast_client.get_nowait() == {"sequence": 1}
    broker.publish({"sequence": 2})
    broker.publish({"sequence": 3})

    assert slow_client.get_nowait() == {"sequence": 3}
    assert fast_client.get_nowait() == {"sequence": 3}


def test_broker_removes_a_closed_client_subscription() -> None:
    broker = LiveEventBroker()
    subscription = broker.subscribe()

    assert broker.subscription_count() == 1
    broker.unsubscribe(subscription)
    broker.publish({"event_type": "scan_update"})

    assert broker.subscription_count() == 0