from __future__ import annotations

from app.serial.protocol import (
    DeviceReadyMessage,
    ProtocolParser,
    ProtocolParserStatistics,
    ScanErrorMessage,
    ScanResultMessage,
)


def test_parser_normalizes_a_valid_scan_result() -> None:
    parser = ProtocolParser()

    message = parser.parse_line(
        """{
        "protocol_version": 1,
        "message_type": "scan_result",
        "scan_id": 42,
        "device_timestamp_ms": 123456,
        "ignored_future_field": true,
        "networks": [{
            "ssid": "example-network",
            "bssid": "aa:bb:cc:dd:ee:ff",
            "rssi_dbm": -52,
            "channel": 6,
            "encryption": "Encrypted"
        }]
        }"""
    )

    assert isinstance(message, ScanResultMessage)
    assert message.networks[0].bssid == "AA:BB:CC:DD:EE:FF"
    assert parser.statistics().accepted_messages == 1


def test_parser_accepts_a_terminal_scan_error_in_the_scan_sequence() -> None:
    parser = ProtocolParser()

    message = parser.parse_line(
        """{
        "protocol_version": 1,
        "message_type": "scan_error",
        "scan_id": 1,
        "device_timestamp_ms": 10,
        "error_code": "wifi_scan_failed",
        "message": "WiFi.scanNetworks returned -1."
        }"""
    )

    assert isinstance(message, ScanErrorMessage)
    assert message.scan_id == 1


def test_device_ready_resets_the_firmware_scan_id_sequence() -> None:
    parser = ProtocolParser()
    parser.parse_line(
        '{"protocol_version":1,"message_type":"scan_result","scan_id":4,'
        '"device_timestamp_ms":100,"networks":[]}'
    )
    ready = parser.parse_line(
        '{"protocol_version":1,"message_type":"device_ready",'
        '"device_id":"esp32-ABC","firmware_version":"0.1.0",'
        '"device_timestamp_ms":1}'
    )
    restarted_scan = parser.parse_line(
        '{"protocol_version":1,"message_type":"scan_result","scan_id":1,'
        '"device_timestamp_ms":2,"networks":[]}'
    )

    assert isinstance(ready, DeviceReadyMessage)
    assert isinstance(restarted_scan, ScanResultMessage)
    assert parser.statistics().duplicate_scan_ids == 0


def test_parser_rejects_duplicate_or_out_of_order_terminal_scan_ids() -> None:
    parser = ProtocolParser()
    first = parser.parse_line(
        '{"protocol_version":1,"message_type":"scan_result","scan_id":2,'
        '"device_timestamp_ms":100,"networks":[]}'
    )
    duplicate = parser.parse_line(
        '{"protocol_version":1,"message_type":"scan_error","scan_id":2,'
        '"device_timestamp_ms":101,"error_code":"wifi_scan_failed",'
        '"message":"failed"}'
    )
    older = parser.parse_line(
        '{"protocol_version":1,"message_type":"scan_result","scan_id":1,'
        '"device_timestamp_ms":102,"networks":[]}'
    )

    assert isinstance(first, ScanResultMessage)
    assert duplicate is None
    assert older is None
    assert parser.statistics().duplicate_scan_ids == 2


def test_parser_rejects_malformed_invalid_unsupported_and_unknown_messages() -> None:
    parser = ProtocolParser()

    assert parser.parse_line('{"protocol_version":1') is None
    assert parser.parse_line('[]') is None
    assert parser.parse_line(
        '{"protocol_version":2,"message_type":"heartbeat",'
        '"device_timestamp_ms":1,"scan_in_progress":false}'
    ) is None
    assert parser.parse_line(
        '{"protocol_version":1,"message_type":"future_message",'
        '"device_timestamp_ms":1}'
    ) is None
    assert parser.parse_line(
        '{"protocol_version":1,"message_type":"scan_result","scan_id":1,'
        '"device_timestamp_ms":1,"networks":[{"ssid":"network",'
        '"bssid":"AA-BB-CC-DD-EE-FF","rssi_dbm":-52,"channel":6,'
        '"encryption":"Encrypted"}]}'
    ) is None

    assert parser.statistics() == ProtocolParserStatistics(
        accepted_messages=0,
        malformed_json=1,
        invalid_messages=2,
        unsupported_versions=1,
        unknown_message_types=1,
        duplicate_scan_ids=0,
    )