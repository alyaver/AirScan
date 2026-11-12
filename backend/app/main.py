"""FastAPI entry point for the local AirScan backend."""

from __future__ import annotations

import asyncio
from datetime import datetime
from queue import Empty
from typing import Any

from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.live.events import LiveEventBroker
from app.serial.manager import (
    SerialConnectionDetails,
    SerialConnectionError,
    SerialPortDetails,
    SerialPortManager,
)
from app.serial.protocol import NetworkObservation, ProtocolParser
from app.serial.state import ConnectionState, ConnectionStateTracker


class HealthResponse(BaseModel):
    """Minimal response used to verify that the backend is available."""

    status: str
    service: str
    host: str
    port: int


class SerialPortResponse(BaseModel):
    """A serial port detected on the local computer."""

    device: str
    description: str
    hardware_id: str
    manufacturer: str | None
    product: str | None
    serial_number: str | None


class SerialPortsResponse(BaseModel):
    """The currently detected serial ports."""

    ports: list[SerialPortResponse]


class SerialConnectionResponse(BaseModel):
    """The local serial-port selection and connection state."""

    selected_port: str | None
    connected: bool
    baud_rate: int


class SerialConnectionRequest(BaseModel):
    """A port chosen by the local user."""

    port: str = Field(min_length=1, max_length=256)


class SerialDeviceStateResponse(BaseModel):
    """Current ESP32 USB serial/device state, never Wi-Fi association state."""

    state: ConnectionState
    selected_port: str | None
    device_id: str | None
    firmware_version: str | None
    last_message_at: datetime | None
    last_scan_at: datetime | None
    last_error: str | None


class ProtocolDiagnosticsResponse(BaseModel):
    """Counts of accepted and rejected serial protocol lines."""

    accepted_messages: int
    malformed_json: int
    invalid_messages: int
    unsupported_versions: int
    unknown_message_types: int
    duplicate_scan_ids: int


class ReaderDiagnosticsResponse(BaseModel):
    """Health counters for the active or most recently stopped serial reader."""

    running: bool
    received_lines: int
    decode_errors: int
    handler_errors: int
    read_errors: int


class DeviceStatusResponse(SerialDeviceStateResponse):
    """Device/transport state plus parser and serial-reader diagnostics."""

    parser: ProtocolDiagnosticsResponse
    reader: ReaderDiagnosticsResponse | None


class LatestScanResponse(BaseModel):
    """Most recent successful scan or terminal scan error in memory."""

    scan_id: int | None
    completed_at: datetime | None
    networks: list[NetworkObservation]
    error_code: str | None
    error_message: str | None


class LiveScanResponse(BaseModel):
    """Immediate frontend snapshot of current connection and scan observations."""

    connection_state: ConnectionState
    last_scan_at: datetime | None
    networks: list[NetworkObservation]
    scan_count: int
    error: str | None


def _live_event_payload(
    event_type: str,
    connection_state: ConnectionStateTracker,
) -> dict[str, Any]:
    """Create one JSON-ready event from an atomic tracker snapshot."""

    details = connection_state.details()
    live = connection_state.live_scan()
    latest_scan = connection_state.latest_scan()
    return {
        "event_type": event_type,
        "connection": SerialDeviceStateResponse(**details.__dict__).model_dump(mode="json"),
        "live": LiveScanResponse(**live.__dict__).model_dump(mode="json"),
        "latest_scan": LatestScanResponse(**latest_scan.__dict__).model_dump(mode="json"),
    }


def create_app(
    settings: Settings | None = None,
    serial_manager: SerialPortManager | None = None,
    protocol_parser: ProtocolParser | None = None,
    connection_state: ConnectionStateTracker | None = None,
    live_event_broker: LiveEventBroker | None = None,
) -> FastAPI:
    """Create the local AirScan API application."""

    resolved_settings = settings or get_settings()
    application = FastAPI(
        title="AirScan Local Backend",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
    )
    application.state.settings = resolved_settings
    application.state.connection_state = connection_state or ConnectionStateTracker()
    application.state.live_event_broker = live_event_broker or LiveEventBroker()

    def publish_live_event(
        event_type: str,
        _details: object,
        _live: object,
        _latest_scan: object,
    ) -> None:
        application.state.live_event_broker.publish(
            _live_event_payload(event_type, application.state.connection_state)
        )

    application.state.connection_state.set_event_handler(publish_live_event)
    application.state.protocol_parser = protocol_parser or ProtocolParser(
        message_handler=application.state.connection_state.record_message
    )
    application.state.serial_manager = serial_manager or SerialPortManager(
        baud_rate=resolved_settings.serial_baud_rate,
        selected_port=resolved_settings.serial_port,
        line_handler=application.state.protocol_parser.parse_line,
        lifecycle_handler=application.state.connection_state.record_lifecycle,
    )

    @application.get("/api/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        """Return backend availability and non-sensitive local configuration."""

        return HealthResponse(
            status="ok",
            service="airscan-backend",
            host=resolved_settings.host,
            port=resolved_settings.port,
        )

    @application.get(
        "/api/serial/ports",
        response_model=SerialPortsResponse,
        tags=["serial"],
    )
    def serial_ports() -> SerialPortsResponse:
        """List serial ports without opening or claiming a device."""

        manager: SerialPortManager = application.state.serial_manager
        return SerialPortsResponse(
            ports=[SerialPortResponse(**port.__dict__) for port in manager.list_ports()]
        )

    @application.get(
        "/api/serial/connection",
        response_model=SerialConnectionResponse,
        tags=["serial"],
    )
    def serial_connection() -> SerialConnectionResponse:
        """Return the selected serial port and current local connection state."""

        manager: SerialPortManager = application.state.serial_manager
        return SerialConnectionResponse(**manager.connection_details().__dict__)

    @application.get(
        "/api/serial/state",
        response_model=SerialDeviceStateResponse,
        tags=["serial"],
    )
    def serial_state() -> SerialDeviceStateResponse:
        """Return USB serial/device activity; this does not describe Wi-Fi association."""

        tracker: ConnectionStateTracker = application.state.connection_state
        return SerialDeviceStateResponse(**tracker.details().__dict__)

    @application.get(
        "/api/device/status",
        response_model=DeviceStatusResponse,
        tags=["device"],
    )
    def device_status() -> DeviceStatusResponse:
        """Return device activity and non-fatal serial parser/reader diagnostics."""

        tracker: ConnectionStateTracker = application.state.connection_state
        parser: ProtocolParser = application.state.protocol_parser
        manager: SerialPortManager = application.state.serial_manager
        reader_statistics = manager.reader_statistics()
        return DeviceStatusResponse(
            **tracker.details().__dict__,
            parser=ProtocolDiagnosticsResponse(**parser.statistics().__dict__),
            reader=(
                ReaderDiagnosticsResponse(**reader_statistics.__dict__)
                if reader_statistics is not None
                else None
            ),
        )

    @application.get(
        "/api/scans/latest",
        response_model=LatestScanResponse,
        tags=["scans"],
    )
    def latest_scan() -> LatestScanResponse:
        """Return the most recent accepted terminal scan, without persistent history."""

        tracker: ConnectionStateTracker = application.state.connection_state
        return LatestScanResponse(**tracker.latest_scan().__dict__)

    @application.get(
        "/api/live",
        response_model=LiveScanResponse,
        tags=["live"],
    )
    def live_scan() -> LiveScanResponse:
        """Return the current snapshot immediately; never wait for another scan."""

        tracker: ConnectionStateTracker = application.state.connection_state
        return LiveScanResponse(**tracker.live_scan().__dict__)

    @application.websocket("/api/live")
    async def live_scan_events(websocket: WebSocket) -> None:
        """Push current and subsequent live snapshots without blocking serial ingestion."""

        await websocket.accept()
        broker: LiveEventBroker = application.state.live_event_broker
        subscription = broker.subscribe()
        try:
            await websocket.send_json(
                _live_event_payload("snapshot", application.state.connection_state)
            )
            while True:
                try:
                    event = await asyncio.to_thread(subscription.get, True, 0.1)
                except Empty:
                    # Yield periodically so a disconnected client can cancel this task.
                    continue
                await websocket.send_json(event)
        except WebSocketDisconnect:
            pass
        finally:
            broker.unsubscribe(subscription)

    @application.put(
        "/api/serial/connection",
        response_model=SerialConnectionResponse,
        tags=["serial"],
    )
    def connect_serial_port(request: SerialConnectionRequest) -> SerialConnectionResponse:
        """Select, open, and begin reading one serial port."""

        manager: SerialPortManager = application.state.serial_manager
        try:
            connection = manager.connect(request.port)
        except SerialConnectionError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error

        return SerialConnectionResponse(**connection.__dict__)

    @application.post(
        "/api/serial/reconnect",
        response_model=SerialConnectionResponse,
        tags=["serial"],
    )
    def reconnect_serial_port() -> SerialConnectionResponse:
        """Explicitly retry the retained selected port after a disconnect or error."""

        manager: SerialPortManager = application.state.serial_manager
        try:
            connection = manager.reconnect()
        except SerialConnectionError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error

        return SerialConnectionResponse(**connection.__dict__)

    @application.delete(
        "/api/serial/connection",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["serial"],
    )
    def disconnect_serial_port() -> Response:
        """Close the selected serial port without changing the selection."""

        manager: SerialPortManager = application.state.serial_manager
        manager.close()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return application


app = create_app()