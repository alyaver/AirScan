"""Safe ownership of the one serial connection used by the AirScan backend."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any, Callable, Iterable

import serial
from serial.tools import list_ports

from app.serial.reader import SerialLineReader, SerialReaderStatistics


@dataclass(frozen=True)
class SerialPortDetails:
    """Metadata reported by the operating system for a serial port."""

    device: str
    description: str
    hardware_id: str
    manufacturer: str | None
    product: str | None
    serial_number: str | None


@dataclass(frozen=True)
class SerialConnectionDetails:
    """The backend's current single-port connection state."""

    selected_port: str | None
    connected: bool
    baud_rate: int


class SerialConnectionError(RuntimeError):
    """Raised when a selected serial port cannot be opened."""


class SerialPortManager:
    """Enumerate ports and ensure the backend owns at most one open port."""

    def __init__(
        self,
        baud_rate: int,
        selected_port: str | None = None,
        port_lister: Callable[[], Iterable[Any]] = list_ports.comports,
        serial_factory: Callable[..., Any] = serial.Serial,
        line_handler: Callable[[str], None] | None = None,
        lifecycle_handler: Callable[[str, str | None, Exception | None], None] | None = None,
        reader_factory: Callable[
            [Any, Callable[[str], None], Callable[[Exception], None]], SerialLineReader
        ] = SerialLineReader,
    ) -> None:
        self._baud_rate = baud_rate
        self._selected_port = selected_port
        self._port_lister = port_lister
        self._serial_factory = serial_factory
        self._line_handler = line_handler or (lambda _: None)
        self._lifecycle_handler = lifecycle_handler or (lambda _event, _port, _error: None)
        self._reader_factory = reader_factory
        self._connection: Any | None = None
        self._reader: SerialLineReader | None = None
        self._lock = RLock()

    def list_ports(self) -> list[SerialPortDetails]:
        """Return detected ports in a stable order without opening any of them."""

        ports = [
            SerialPortDetails(
                device=port.device,
                description=port.description or "",
                hardware_id=port.hwid or "",
                manufacturer=getattr(port, "manufacturer", None),
                product=getattr(port, "product", None),
                serial_number=getattr(port, "serial_number", None),
            )
            for port in self._port_lister()
        ]
        return sorted(ports, key=lambda port: port.device.casefold())

    def connection_details(self) -> SerialConnectionDetails:
        """Return the selected port and whether it is currently open."""

        with self._lock:
            return SerialConnectionDetails(
                selected_port=self._selected_port,
                connected=self._is_connection_open(),
                baud_rate=self._baud_rate,
            )

    def connect(self, port: str | None = None) -> SerialConnectionDetails:
        """Open a selected port once, replacing a previous open port if necessary."""

        requested_port = (port or self._selected_port or "").strip()
        if not requested_port:
            raise SerialConnectionError("Select a serial port before connecting.")

        with self._lock:
            if self._is_connection_open() and self._selected_port == requested_port:
                return self.connection_details()

            self._close_unlocked()
            self._selected_port = requested_port
            self._notify_lifecycle("connecting")

            try:
                self._connection = self._serial_factory(
                    port=requested_port,
                    baudrate=self._baud_rate,
                    timeout=1,
                )
            except (serial.SerialException, OSError) as error:
                self._connection = None
                self._notify_lifecycle("error", error)
                raise SerialConnectionError(
                    f"Could not open serial port {requested_port}: {error}"
                ) from error

            self._reader = self._reader_factory(
                self._connection,
                self._line_handler,
                lambda error, connection=self._connection: self._handle_reader_error(
                    connection,
                    error,
                ),
            )
            self._reader.start()
            self._notify_lifecycle("connected")
            return self.connection_details()

    def reconnect(self) -> SerialConnectionDetails:
        """Retry opening the retained selected port after a controlled failure."""

        with self._lock:
            if not self._selected_port:
                raise SerialConnectionError("Select a serial port before reconnecting.")
            requested_port = self._selected_port
            self._notify_lifecycle("reconnecting")

        return self.connect(requested_port)

    def close(self) -> SerialConnectionDetails:
        """Close the open port while retaining the user-selected port."""

        with self._lock:
            self._close_unlocked()
            return self.connection_details()

    def reader_statistics(self) -> SerialReaderStatistics | None:
        """Return diagnostics for the active or most recently stopped reader."""

        with self._lock:
            return self._reader.statistics() if self._reader is not None else None

    def _is_connection_open(self) -> bool:
        return self._connection is not None and bool(
            getattr(self._connection, "is_open", False)
        )

    def _close_unlocked(self) -> None:
        if self._reader is not None:
            self._reader.stop()
            self._reader = None
        if self._connection is not None:
            self._connection.close()
        self._connection = None
        self._notify_lifecycle("disconnected")

    def _handle_reader_error(self, connection: Any, error: Exception) -> None:
        """Mark a disconnected or failed port unavailable without crashing the backend."""

        with self._lock:
            if self._connection is not connection:
                return

            try:
                connection.close()
            except Exception:
                pass
            self._connection = None
            self._notify_lifecycle("error", error)

    def _notify_lifecycle(self, event: str, error: Exception | None = None) -> None:
        try:
            self._lifecycle_handler(event, self._selected_port, error)
        except Exception:
            # Observer failures must not prevent safe serial-port ownership.
            pass