"""In-memory ESP32 serial connection state for the local AirScan API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Callable

from app.serial.protocol import (
    DeviceErrorMessage,
    DeviceReadyMessage,
    HeartbeatMessage,
    NetworkObservation,
    ProtocolMessage,
    ScanErrorMessage,
    ScanResultMessage,
)


class ConnectionState(str, Enum):
    """User-visible state of the selected USB serial device."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED_IDLE = "CONNECTED_IDLE"
    CONNECTED_SCANNING = "CONNECTED_SCANNING"
    RECONNECTING = "RECONNECTING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ConnectionStateDetails:
    """Snapshot of current serial/device state for REST clients."""

    state: ConnectionState
    selected_port: str | None
    device_id: str | None
    firmware_version: str | None
    last_message_at: datetime | None
    last_scan_at: datetime | None
    last_error: str | None


@dataclass(frozen=True)
class LatestScanDetails:
    """Normalized data from the most recent accepted terminal scan."""

    scan_id: int | None
    completed_at: datetime | None
    networks: tuple[NetworkObservation, ...]
    error_code: str | None
    error_message: str | None


@dataclass(frozen=True)
class LiveScanDetails:
    """One atomic live-monitoring snapshot without persistence or polling waits."""

    connection_state: ConnectionState
    last_scan_at: datetime | None
    networks: tuple[NetworkObservation, ...]
    scan_count: int
    error: str | None


class ConnectionStateTracker:
    """Translate serial lifecycle and accepted protocol messages into state."""

    def __init__(
        self,
        event_handler: Callable[
            [str, ConnectionStateDetails, LiveScanDetails, LatestScanDetails], None
        ]
        | None = None,
    ) -> None:
        self._state = ConnectionState.DISCONNECTED
        self._selected_port: str | None = None
        self._device_id: str | None = None
        self._firmware_version: str | None = None
        self._last_message_at: datetime | None = None
        self._last_scan_at: datetime | None = None
        self._last_error: str | None = None
        self._last_scan_id: int | None = None
        self._latest_networks: tuple[NetworkObservation, ...] = ()
        self._last_scan_error_code: str | None = None
        self._last_scan_error_message: str | None = None
        self._scan_count_since_connection = 0
        self._event_handler = event_handler or (lambda _kind, _details, _live, _scan: None)
        self._lock = Lock()

    def record_lifecycle(
        self,
        event: str,
        selected_port: str | None,
        error: Exception | None = None,
    ) -> None:
        """Record an open, close, reconnect, or reader-error lifecycle event."""

        with self._lock:
            self._selected_port = selected_port

            if event == "connecting":
                self._state = ConnectionState.CONNECTING
                self._last_error = None
                self._reset_live_scan_state()
            elif event == "connected":
                self._state = ConnectionState.CONNECTED_IDLE
                self._last_error = None
            elif event == "reconnecting":
                self._state = ConnectionState.RECONNECTING
                self._last_error = None
            elif event == "disconnected":
                self._state = ConnectionState.DISCONNECTED
                self._device_id = None
                self._firmware_version = None
                self._last_message_at = None
                self._last_error = None
                self._reset_live_scan_state()
            elif event == "error":
                self._state = ConnectionState.ERROR
                self._last_error = str(error) if error is not None else "Serial connection failed."
            else:
                raise ValueError(f"Unsupported serial lifecycle event: {event}")

            details, live, latest_scan = self._snapshots_unlocked()

        self._notify("connection_state", details, live, latest_scan)

    def record_message(self, message: ProtocolMessage) -> None:
        """Update state only after the parser accepts a normalized message."""

        now = datetime.now(timezone.utc)
        with self._lock:
            self._last_message_at = now

            if isinstance(message, DeviceReadyMessage):
                self._device_id = message.device_id
                self._firmware_version = message.firmware_version
                self._state = ConnectionState.CONNECTED_IDLE
                self._last_error = None
            elif isinstance(message, HeartbeatMessage):
                self._state = (
                    ConnectionState.CONNECTED_SCANNING
                    if message.scan_in_progress
                    else ConnectionState.CONNECTED_IDLE
                )
            elif isinstance(message, ScanResultMessage):
                self._state = ConnectionState.CONNECTED_IDLE
                self._last_scan_at = now
                self._last_scan_id = message.scan_id
                self._latest_networks = tuple(message.networks)
                self._last_scan_error_code = None
                self._last_scan_error_message = None
                self._scan_count_since_connection += 1
            elif isinstance(message, ScanErrorMessage):
                self._state = ConnectionState.CONNECTED_IDLE
                self._last_scan_at = now
                self._last_scan_id = message.scan_id
                self._latest_networks = ()
                self._last_scan_error_code = message.error_code
                self._last_scan_error_message = message.message
                self._last_error = f"{message.error_code}: {message.message}"
                self._scan_count_since_connection += 1
            elif isinstance(message, DeviceErrorMessage):
                self._state = ConnectionState.ERROR
                self._last_error = f"{message.error_code}: {message.message}"

            details, live, latest_scan = self._snapshots_unlocked()

        event_kind = (
            "scan_update"
            if isinstance(message, (ScanResultMessage, ScanErrorMessage))
            else "connection_state"
        )
        self._notify(event_kind, details, live, latest_scan)

    def set_event_handler(
        self,
        event_handler: Callable[
            [str, ConnectionStateDetails, LiveScanDetails, LatestScanDetails], None
        ],
    ) -> None:
        """Replace the optional observer without exposing mutable state."""

        with self._lock:
            self._event_handler = event_handler

    def details(self) -> ConnectionStateDetails:
        """Return an atomic state snapshot for the local API."""

        with self._lock:
            return self._snapshots_unlocked()[0]

    def latest_scan(self) -> LatestScanDetails:
        """Return the latest scan result or terminal scan error without history storage."""

        with self._lock:
            return self._snapshots_unlocked()[2]

    def live_scan(self) -> LiveScanDetails:
        """Return the current non-blocking live-monitoring snapshot."""

        with self._lock:
            return self._snapshots_unlocked()[1]

    def _snapshots_unlocked(
        self,
    ) -> tuple[ConnectionStateDetails, LiveScanDetails, LatestScanDetails]:
        """Build mutually consistent snapshots while the caller holds ``_lock``."""

        details = ConnectionStateDetails(
            state=self._state,
            selected_port=self._selected_port,
            device_id=self._device_id,
            firmware_version=self._firmware_version,
            last_message_at=self._last_message_at,
            last_scan_at=self._last_scan_at,
            last_error=self._last_error,
        )
        live = LiveScanDetails(
            connection_state=self._state,
            last_scan_at=self._last_scan_at,
            networks=self._latest_networks,
            scan_count=self._scan_count_since_connection,
            error=self._last_error,
        )
        latest_scan = LatestScanDetails(
            scan_id=self._last_scan_id,
            completed_at=self._last_scan_at,
            networks=self._latest_networks,
            error_code=self._last_scan_error_code,
            error_message=self._last_scan_error_message,
        )
        return details, live, latest_scan

    def _notify(
        self,
        event_kind: str,
        details: ConnectionStateDetails,
        live: LiveScanDetails,
        latest_scan: LatestScanDetails,
    ) -> None:
        try:
            self._event_handler(event_kind, details, live, latest_scan)
        except Exception:
            # UI observers must not affect serial connection or protocol processing.
            pass

    def _reset_live_scan_state(self) -> None:
        """Clear observations which must not carry over to another connection."""

        self._last_scan_at = None
        self._last_scan_id = None
        self._latest_networks = ()
        self._last_scan_error_code = None
        self._last_scan_error_message = None
        self._scan_count_since_connection = 0