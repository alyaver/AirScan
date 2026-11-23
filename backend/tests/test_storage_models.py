from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.storage.models import (
    MasterScanRecord,
    RecoveryStatus,
    ScanObservation,
    SessionMetadata,
)


UTC_TIMESTAMP = datetime(2026, 11, 18, 18, 30, 5, 142000, tzinfo=timezone.utc)
NETWORK = {
    "ssid": "example-network",
    "bssid": "aa:bb:cc:dd:ee:ff",
    "rssi_dbm": -52,
    "channel": 6,
    "encryption": "Encrypted",
}


def test_recording_models_round_trip_through_json_with_one_network_schema() -> None:
    observation = ScanObservation(
        recorded_at=UTC_TIMESTAMP,
        scan_id=42,
        networks=[NETWORK],
    )
    session = SessionMetadata(
        session_id="session-123",
        label="Baseline",
        started_at=UTC_TIMESTAMP,
        ended_at=UTC_TIMESTAMP,
        duration_seconds=0,
        scan_count=1,
        unique_bssid_count=1,
        status="completed",
    )
    master_record = MasterScanRecord(session_id=session.session_id, **observation.model_dump())
    recovery = RecoveryStatus(
        session_id=session.session_id,
        status="pending",
        detected_at=UTC_TIMESTAMP,
    )

    assert ScanObservation.model_validate_json(observation.model_dump_json()) == observation
    assert SessionMetadata.model_validate_json(session.model_dump_json()) == session
    assert MasterScanRecord.model_validate_json(master_record.model_dump_json()) == master_record
    assert RecoveryStatus.model_validate_json(recovery.model_dump_json()) == recovery
    assert master_record.model_dump(mode="json") == {
        "record_type": "scan",
        "schema_version": 1,
        "session_id": "session-123",
        "recorded_at": "2026-11-18T18:30:05.142000Z",
        "scan_id": 42,
        "networks": [{**NETWORK, "bssid": "AA:BB:CC:DD:EE:FF"}],
    }
    assert json.loads(master_record.model_dump_json())["networks"][0]["bssid"] == "AA:BB:CC:DD:EE:FF"


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (ScanObservation, {"recorded_at": UTC_TIMESTAMP, "scan_id": 0, "networks": []}),
        (ScanObservation, {"recorded_at": "2026-11-18T18:30:05", "scan_id": 1, "networks": []}),
        (
            MasterScanRecord,
            {
                "session_id": "session-123",
                "recorded_at": UTC_TIMESTAMP,
                "scan_id": 1,
                "networks": [{**NETWORK, "channel": 0}],
            },
        ),
        (
            SessionMetadata,
            {
                "session_id": "",
                "label": "Baseline",
                "started_at": UTC_TIMESTAMP,
                "status": "completed",
            },
        ),
        (
            RecoveryStatus,
            {
                "schema_version": 2,
                "session_id": "session-123",
                "status": "pending",
                "detected_at": UTC_TIMESTAMP,
            },
        ),
    ],
)
def test_recording_models_reject_missing_or_invalid_required_values(
    model: type[ScanObservation | MasterScanRecord | SessionMetadata | RecoveryStatus],
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_storage_models_reject_unknown_fields_and_are_immutable() -> None:
    observation = ScanObservation(
        recorded_at=UTC_TIMESTAMP,
        scan_id=42,
        networks=[],
    )

    with pytest.raises(ValidationError):
        ScanObservation.model_validate({**observation.model_dump(), "unexpected": True})
    with pytest.raises(ValidationError):
        observation.scan_id = 43