"""Version-1 AirScan serial protocol models and validation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from threading import Lock
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


PROTOCOL_VERSION = 1
_BSSID_PATTERN = re.compile(r"^[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}$")


class ProtocolModel(BaseModel):
    """Base model that permits forward-compatible optional message fields."""

    model_config = ConfigDict(extra="ignore", strict=True)


class MessageEnvelope(ProtocolModel):
    """Fields required on every version-1 protocol message."""

    protocol_version: Literal[PROTOCOL_VERSION]
    message_type: str
    device_timestamp_ms: Annotated[int, Field(ge=0)]


class DeviceReadyMessage(MessageEnvelope):
    """Firmware-session boundary emitted after device initialization."""

    message_type: Literal["device_ready"]
    device_id: Annotated[str, Field(min_length=1)]
    firmware_version: Annotated[str, Field(min_length=1)]


class HeartbeatMessage(MessageEnvelope):
    """Optional firmware responsiveness message."""

    message_type: Literal["heartbeat"]
    scan_in_progress: bool


class NetworkObservation(ProtocolModel):
    """One normalized Wi-Fi network observation from a completed scan."""

    ssid: str
    bssid: str
    rssi_dbm: int
    channel: Annotated[int, Field(gt=0)]
    encryption: Literal["Open", "Encrypted"]

    @field_validator("bssid")
    @classmethod
    def normalize_bssid(cls, value: str) -> str:
        """Accept canonical separators and normalize hexadecimal case."""

        if not _BSSID_PATTERN.fullmatch(value):
            raise ValueError("BSSID must use colon-separated hexadecimal octets.")
        return value.upper()


class ScanResultMessage(MessageEnvelope):
    """One successful complete Wi-Fi scan, including an allowed empty result."""

    message_type: Literal["scan_result"]
    scan_id: Annotated[int, Field(gt=0)]
    networks: list[NetworkObservation]


class ScanErrorMessage(MessageEnvelope):
    """A terminal error for one attempted Wi-Fi scan."""

    message_type: Literal["scan_error"]
    scan_id: Annotated[int, Field(gt=0)]
    error_code: Annotated[str, Field(min_length=1)]
    message: Annotated[str, Field(min_length=1)]


class DeviceErrorMessage(MessageEnvelope):
    """A device-level error not associated with a particular scan."""

    message_type: Literal["device_error"]
    error_code: Annotated[str, Field(min_length=1)]
    message: Annotated[str, Field(min_length=1)]


ProtocolMessage: TypeAlias = (
    DeviceReadyMessage
    | HeartbeatMessage
    | ScanResultMessage
    | ScanErrorMessage
    | DeviceErrorMessage
)


@dataclass(frozen=True)
class ProtocolParserStatistics:
    """Non-fatal parser outcomes for the current backend process."""

    accepted_messages: int
    malformed_json: int
    invalid_messages: int
    unsupported_versions: int
    unknown_message_types: int
    duplicate_scan_ids: int


class ProtocolParser:
    """Parse, validate, normalize, and sequence version-1 serial messages."""

    def __init__(self) -> None:
        self._accepted_messages = 0
        self._malformed_json = 0
        self._invalid_messages = 0
        self._unsupported_versions = 0
        self._unknown_message_types = 0
        self._duplicate_scan_ids = 0
        self._last_terminal_scan_id: int | None = None
        self._latest_message: ProtocolMessage | None = None
        self._lock = Lock()

    def parse_line(self, line: str) -> ProtocolMessage | None:
        """Return a normalized message or reject a non-fatal invalid line."""

        with self._lock:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                self._malformed_json += 1
                return None

            if not isinstance(payload, dict):
                self._invalid_messages += 1
                return None

            if payload.get("protocol_version") != PROTOCOL_VERSION:
                self._unsupported_versions += 1
                return None

            message_type = payload.get("message_type")
            model_type = {
                "device_ready": DeviceReadyMessage,
                "heartbeat": HeartbeatMessage,
                "scan_result": ScanResultMessage,
                "scan_error": ScanErrorMessage,
                "device_error": DeviceErrorMessage,
            }.get(message_type)
            if model_type is None:
                self._unknown_message_types += 1
                return None

            try:
                message = model_type.model_validate(payload)
            except ValidationError:
                self._invalid_messages += 1
                return None

            if isinstance(message, DeviceReadyMessage):
                self._last_terminal_scan_id = None
            elif isinstance(message, (ScanResultMessage, ScanErrorMessage)):
                if (
                    self._last_terminal_scan_id is not None
                    and message.scan_id <= self._last_terminal_scan_id
                ):
                    self._duplicate_scan_ids += 1
                    return None
                self._last_terminal_scan_id = message.scan_id

            self._accepted_messages += 1
            self._latest_message = message
            return message

    def statistics(self) -> ProtocolParserStatistics:
        """Return a snapshot of parser diagnostics."""

        with self._lock:
            return ProtocolParserStatistics(
                accepted_messages=self._accepted_messages,
                malformed_json=self._malformed_json,
                invalid_messages=self._invalid_messages,
                unsupported_versions=self._unsupported_versions,
                unknown_message_types=self._unknown_message_types,
                duplicate_scan_ids=self._duplicate_scan_ids,
            )

    def latest_message(self) -> ProtocolMessage | None:
        """Return the most recent accepted normalized protocol message."""

        with self._lock:
            return self._latest_message