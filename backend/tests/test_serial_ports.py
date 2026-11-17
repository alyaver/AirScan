from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.serial.manager import SerialPortManager


class FakePort:
    def __init__(self, device: str, description: str, hwid: str) -> None:
        self.device = device
        self.description = description
        self.hwid = hwid
        self.manufacturer = "Espressif"
        self.product = "USB JTAG/serial debug unit"
        self.serial_number = "ABC123"


class FakeConnection:
    def __init__(self) -> None:
        self.is_open = True
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1
        self.is_open = False


def build_client(manager: SerialPortManager) -> TestClient:
    app = create_app(
        Settings(
            host="127.0.0.1",
            port=8000,
            serial_baud_rate=115200,
            serial_port=None,
            data_dir=Path("data"),
        ),
        serial_manager=manager,
    )
    return TestClient(app)


def test_serial_ports_endpoint_lists_detected_ports_in_device_order() -> None:
    manager = SerialPortManager(
        baud_rate=115200,
        port_lister=lambda: [
            FakePort("COM7", "Second device", "USB VID:PID=0002"),
            FakePort("COM3", "First device", "USB VID:PID=0001"),
        ],
    )

    response = build_client(manager).get("/api/serial/ports")

    assert response.status_code == 200
    assert response.json() == {
        "ports": [
            {
                "device": "COM3",
                "description": "First device",
                "hardware_id": "USB VID:PID=0001",
                "manufacturer": "Espressif",
                "product": "USB JTAG/serial debug unit",
                "serial_number": "ABC123",
            },
            {
                "device": "COM7",
                "description": "Second device",
                "hardware_id": "USB VID:PID=0002",
                "manufacturer": "Espressif",
                "product": "USB JTAG/serial debug unit",
                "serial_number": "ABC123",
            },
        ]
    }


def test_serial_connection_endpoint_opens_one_selected_port_only_once() -> None:
    connections: list[FakeConnection] = []

    def serial_factory(**_: object) -> FakeConnection:
        connection = FakeConnection()
        connections.append(connection)
        return connection

    manager = SerialPortManager(baud_rate=115200, serial_factory=serial_factory)
    client = build_client(manager)

    first_response = client.put("/api/serial/connection", json={"port": "COM7"})
    second_response = client.put("/api/serial/connection", json={"port": "COM7"})

    assert first_response.status_code == 200
    assert first_response.json() == {
        "selected_port": "COM7",
        "connected": True,
        "baud_rate": 115200,
    }
    assert second_response.status_code == 200
    assert len(connections) == 1


def test_selecting_another_port_closes_the_previous_connection() -> None:
    connections: list[FakeConnection] = []

    def serial_factory(**_: object) -> FakeConnection:
        connection = FakeConnection()
        connections.append(connection)
        return connection

    manager = SerialPortManager(baud_rate=115200, serial_factory=serial_factory)
    client = build_client(manager)

    client.put("/api/serial/connection", json={"port": "COM7"})
    response = client.put("/api/serial/connection", json={"port": "COM8"})

    assert response.status_code == 200
    assert response.json()["selected_port"] == "COM8"
    assert len(connections) == 2
    assert connections[0].close_calls == 1


def test_connection_endpoint_returns_controlled_error_when_port_cannot_open() -> None:
    def serial_factory(**_: object) -> FakeConnection:
        raise OSError("Access is denied.")

    manager = SerialPortManager(baud_rate=115200, serial_factory=serial_factory)

    response = build_client(manager).put(
        "/api/serial/connection",
        json={"port": "COM7"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Could not open serial port COM7: Access is denied."
    }


def test_disconnect_closes_the_port_and_keeps_the_selection() -> None:
    connection = FakeConnection()
    manager = SerialPortManager(
        baud_rate=115200,
        serial_factory=lambda **_: connection,
    )
    client = build_client(manager)

    client.put("/api/serial/connection", json={"port": "COM7"})
    disconnect_response = client.delete("/api/serial/connection")
    state_response = client.get("/api/serial/connection")

    assert disconnect_response.status_code == 204
    assert connection.close_calls == 1
    assert state_response.json() == {
        "selected_port": "COM7",
        "connected": False,
        "baud_rate": 115200,
    }