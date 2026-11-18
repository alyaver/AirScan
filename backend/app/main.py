"""FastAPI entry point for the local AirScan backend."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.serial.manager import (
    SerialConnectionDetails,
    SerialConnectionError,
    SerialPortDetails,
    SerialPortManager,
)
from app.serial.protocol import ProtocolParser


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


def create_app(
    settings: Settings | None = None,
    serial_manager: SerialPortManager | None = None,
    protocol_parser: ProtocolParser | None = None,
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
    application.state.protocol_parser = protocol_parser or ProtocolParser()
    application.state.serial_manager = serial_manager or SerialPortManager(
        baud_rate=resolved_settings.serial_baud_rate,
        selected_port=resolved_settings.serial_port,
        line_handler=application.state.protocol_parser.parse_line,
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