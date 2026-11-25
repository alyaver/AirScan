from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.storage.jsonl import DuplicateMasterScanRecordError, MasterJsonlWriter
from app.storage.models import MasterScanRecord


UTC_TIMESTAMP = datetime(2026, 11, 18, 18, 30, 5, 142000, tzinfo=timezone.utc)
FIRST_SESSION_ID = "7f2a9c2183ce4fa79ebd7dbdc5f8e9a1"
SECOND_SESSION_ID = "d4ea7b4187ed411eacbbf9e72c2a4d51"


def build_record(session_id: str = FIRST_SESSION_ID, scan_id: int = 1) -> MasterScanRecord:
    return MasterScanRecord(
        session_id=session_id,
        recorded_at=UTC_TIMESTAMP,
        scan_id=scan_id,
        networks=[
            {
                "ssid": "AirScan",
                "bssid": "aa:bb:cc:dd:ee:ff",
                "rssi_dbm": -50,
                "channel": 6,
                "encryption": "Encrypted",
            }
        ],
    )


def read_records(path: Path) -> list[MasterScanRecord]:
    return [
        MasterScanRecord.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def test_writer_does_not_create_data_directory_or_master_file_until_first_append(tmp_path: Path) -> None:
    data_dir = tmp_path / "recording-data"
    writer = MasterJsonlWriter(data_dir)

    assert writer.path == data_dir / "master.jsonl"
    assert data_dir.exists() is False
    assert writer.path.exists() is False

    writer.append(build_record())

    assert writer.path.exists()
    assert read_records(writer.path) == [build_record()]


def test_writer_appends_one_valid_json_record_per_accepted_scan_in_order(tmp_path: Path) -> None:
    writer = MasterJsonlWriter(tmp_path / "recording-data")
    first_record = build_record(scan_id=1)
    second_record = build_record(scan_id=2)

    writer.append(first_record)
    writer.append(second_record)

    assert read_records(writer.path) == [first_record, second_record]
    assert writer.path.read_bytes().endswith(b"\n")


def test_writer_rejects_duplicate_scan_ids_within_one_session(tmp_path: Path) -> None:
    writer = MasterJsonlWriter(tmp_path / "recording-data")
    record = build_record()
    writer.append(record)

    with pytest.raises(DuplicateMasterScanRecordError, match="already written"):
        writer.append(record)

    assert read_records(writer.path) == [record]


def test_writer_allows_matching_scan_ids_from_different_sessions(tmp_path: Path) -> None:
    writer = MasterJsonlWriter(tmp_path / "recording-data")
    first_record = build_record(FIRST_SESSION_ID, scan_id=1)
    second_record = build_record(SECOND_SESSION_ID, scan_id=1)

    writer.append(first_record)
    writer.append(second_record)

    assert read_records(writer.path) == [first_record, second_record]


def test_new_writer_preserves_existing_master_records_for_a_later_append(tmp_path: Path) -> None:
    data_dir = tmp_path / "recording-data"
    first_record = build_record(scan_id=1)
    second_record = build_record(scan_id=2)

    MasterJsonlWriter(data_dir).append(first_record)
    MasterJsonlWriter(data_dir).append(second_record)

    assert read_records(data_dir / "master.jsonl") == [first_record, second_record]


def test_writer_rejects_values_other_than_validated_master_records(tmp_path: Path) -> None:
    writer = MasterJsonlWriter(tmp_path / "recording-data")

    with pytest.raises(TypeError, match="MasterScanRecord"):
        writer.append(object())  # type: ignore[arg-type]

    assert writer.path.exists() is False