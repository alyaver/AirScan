"""Canonical version-1 schemas for recorded AirScan observations.

These models define storage payloads only. They do not read, create, or write
files; live-only monitoring remains memory-only until a recording workflow uses
them in a later task.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.serial.protocol import NetworkObservation, ProtocolModel
from app.storage.naming import SESSION_ID_PATTERN


STORAGE_SCHEMA_VERSION = 1
RecordType = Literal["scan"]
SessionLabel = Literal["Police Observed", "Baseline", "Unknown"]
SessionStatus = Literal["active", "completed", "interrupted", "recovered"]
RecoveryState = Literal["pending", "recovered", "discarded"]
SessionId = Annotated[str, Field(pattern=SESSION_ID_PATTERN)]


class StorageModel(ProtocolModel):
    """Strict, immutable base for all versioned recording schemas."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _require_utc_timestamp(value: datetime) -> datetime:
    """Require timezone-aware UTC timestamps so serialized records are unambiguous."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must include a UTC offset.")
    if value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("Timestamp must use the UTC offset.")
    return value


class ScanObservation(StorageModel):
    """One accepted successful scan at the backend-recorded UTC timestamp."""

    recorded_at: datetime
    scan_id: Annotated[int, Field(gt=0)]
    networks: list[NetworkObservation]

    @field_validator("recorded_at")
    @classmethod
    def validate_recorded_at(cls, value: datetime) -> datetime:
        return _require_utc_timestamp(value)


class SessionMetadata(StorageModel):
    """Session-level metadata shared by temporary and finalized session files."""

    schema_version: Literal[STORAGE_SCHEMA_VERSION] = STORAGE_SCHEMA_VERSION
    session_id: SessionId
    label: SessionLabel
    notes: str = ""
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: Annotated[int | None, Field(ge=0)] = None
    scan_count: Annotated[int, Field(ge=0)] = 0
    unique_bssid_count: Annotated[int, Field(ge=0)] = 0
    status: SessionStatus

    @field_validator("started_at", "ended_at")
    @classmethod
    def validate_session_timestamps(cls, value: datetime | None) -> datetime | None:
        return _require_utc_timestamp(value) if value is not None else None

    @model_validator(mode="after")
    def validate_session_lifecycle(self) -> SessionMetadata:
        """Keep active and finalized metadata states unambiguous."""

        if self.status == "active":
            if self.ended_at is not None or self.duration_seconds is not None:
                raise ValueError("Active sessions must not have an end timestamp or duration.")
            return self

        if self.ended_at is None or self.duration_seconds is None:
            raise ValueError("Finalized sessions must have an end timestamp and duration.")
        if self.ended_at < self.started_at:
            raise ValueError("Session end timestamp must not precede its start timestamp.")
        if self.duration_seconds != int((self.ended_at - self.started_at).total_seconds()):
            raise ValueError("Session duration must equal the elapsed whole seconds.")
        return self


class MasterScanRecord(StorageModel):
    """One append-only master JSONL record for an accepted recorded scan."""

    record_type: RecordType = "scan"
    schema_version: Literal[STORAGE_SCHEMA_VERSION] = STORAGE_SCHEMA_VERSION
    session_id: SessionId
    recorded_at: datetime
    scan_id: Annotated[int, Field(gt=0)]
    networks: list[NetworkObservation]

    @field_validator("recorded_at")
    @classmethod
    def validate_recorded_at(cls, value: datetime) -> datetime:
        return _require_utc_timestamp(value)


class RecoveryStatus(StorageModel):
    """Recovery state for a temporary recording session discovered on startup."""

    schema_version: Literal[STORAGE_SCHEMA_VERSION] = STORAGE_SCHEMA_VERSION
    session_id: SessionId
    status: RecoveryState
    detected_at: datetime
    detail: str | None = None

    @field_validator("detected_at")
    @classmethod
    def validate_detected_at(cls, value: datetime) -> datetime:
        return _require_utc_timestamp(value)