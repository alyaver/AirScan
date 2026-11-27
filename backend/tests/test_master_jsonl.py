from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.storage.jsonl import (
    DuplicateMasterScanRecordError,
    MasterJsonlIntegrityError,
    MasterJsonlWriter,
    inspect_master_jsonl,
    repair_master_jsonl,
)
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


def test_inspection_reports_a_clean_master_file_and_a_missing_master_file(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing" / "master.jsonl"
    missing_report = inspect_master_jsonl(missing_path)

    assert missing_report.exists is False
    assert missing_report.is_clean is False
    assert missing_report.valid_record_count == 0

    writer = MasterJsonlWriter(tmp_path / "recording-data")
    writer.append(build_record())
    clean_report = inspect_master_jsonl(writer.path)

    assert clean_report.is_clean is True
    assert clean_report.valid_record_count == 1
    assert clean_report.final_incomplete_line is False
    assert clean_report.issues == ()


def test_inspection_and_repair_handle_a_crash_truncated_final_line(tmp_path: Path) -> None:
    source_path = tmp_path / "recording-data" / "master.jsonl"
    source_path.parent.mkdir()
    valid_line = build_record().model_dump_json().encode()
    source_path.write_bytes(valid_line + b"\n{\"record_type\":\"scan\"")
    repaired_path = tmp_path / "recovered" / "master.repaired.jsonl"

    report = inspect_master_jsonl(source_path)
    returned_report = repair_master_jsonl(source_path, repaired_path)

    assert report.final_incomplete_line is True
    assert report.valid_record_count == 1
    assert report.issues == ()
    assert returned_report == report
    assert read_records(repaired_path) == [build_record()]
    assert source_path.read_bytes() == valid_line + b"\n{\"record_type\":\"scan\""


def test_inspection_reports_malformed_complete_lines_and_safe_repair_refuses_to_drop_them(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "recording-data" / "master.jsonl"
    source_path.parent.mkdir()
    first_record = build_record(scan_id=1)
    second_record = build_record(scan_id=2)
    source_path.write_text(
        f"{first_record.model_dump_json()}\nnot json\n{second_record.model_dump_json()}\n",
        encoding="utf-8",
        newline="\n",
    )
    repaired_path = tmp_path / "recovered" / "master.repaired.jsonl"

    report = inspect_master_jsonl(source_path)

    assert report.is_clean is False
    assert report.valid_record_count == 2
    assert report.final_incomplete_line is False
    assert len(report.issues) == 1
    assert report.issues[0].line_number == 2
    with pytest.raises(MasterJsonlIntegrityError, match="Refusing"):
        repair_master_jsonl(source_path, repaired_path)
    assert repaired_path.exists() is False

    repair_master_jsonl(source_path, repaired_path, allow_nonfinal_issues=True)

    assert read_records(repaired_path) == [first_record, second_record]
    assert source_path.read_text(encoding="utf-8") == (
        f"{first_record.model_dump_json()}\nnot json\n{second_record.model_dump_json()}\n"
    )


def test_repair_rejects_replacing_its_source_file(tmp_path: Path) -> None:
    source_path = tmp_path / "recording-data" / "master.jsonl"
    source_path.parent.mkdir()
    source_path.write_text(f"{build_record().model_dump_json()}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="differ"):
        repair_master_jsonl(source_path, source_path)