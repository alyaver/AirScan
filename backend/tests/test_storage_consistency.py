from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.storage.consistency import inspect_storage_consistency
from app.storage.jsonl import MasterJsonlWriter
from app.storage.models import MasterScanRecord, ScanObservation, SessionMetadata
from app.storage.sessions import TemporarySessionWriter


UTC_TIMESTAMP = datetime(2026, 11, 18, 18, 30, 5, tzinfo=timezone.utc)
FIRST_SESSION_ID = "7f2a9c2183ce4fa79ebd7dbdc5f8e9a1"
SECOND_SESSION_ID = "d4ea7b4187ed411eacbbf9e72c2a4d51"


def build_metadata(session_id: str = FIRST_SESSION_ID) -> SessionMetadata:
    return SessionMetadata(
        session_id=session_id,
        label="Baseline",
        started_at=UTC_TIMESTAMP,
        status="active",
    )


def build_observation(scan_id: int) -> ScanObservation:
    return ScanObservation(
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


def finalize_session(data_dir: Path, session_id: str, scan_ids: list[int]) -> Path:
    writer = TemporarySessionWriter(data_dir, build_metadata(session_id))
    for scan_id in scan_ids:
        writer.append(build_observation(scan_id))
    return writer.finalize(UTC_TIMESTAMP + timedelta(seconds=60))


def append_master_records(data_dir: Path, session_id: str, scan_ids: list[int]) -> None:
    writer = MasterJsonlWriter(data_dir)
    for scan_id in scan_ids:
        observation = build_observation(scan_id)
        writer.append(MasterScanRecord(session_id=session_id, **observation.model_dump()))


def test_consistency_report_has_no_false_discrepancies_for_matching_finalized_session(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "recording-data"
    session_path = finalize_session(data_dir, FIRST_SESSION_ID, [1, 2])
    append_master_records(data_dir, FIRST_SESSION_ID, [1, 2])

    report = inspect_storage_consistency(data_dir)

    assert report.is_consistent is True
    assert report.master_path == data_dir / "master.jsonl"
    assert report.session_file_issues == ()
    assert len(report.sessions) == 1
    comparison = report.sessions[0]
    assert comparison.session_id == FIRST_SESSION_ID
    assert comparison.session_path == session_path
    assert comparison.session_declared_scan_count == 2
    assert comparison.session_observation_count == 2
    assert comparison.master_record_count == 2
    assert comparison.missing_from_master == ()
    assert comparison.missing_from_session == ()
    assert comparison.duplicate_session_scan_ids == ()
    assert comparison.duplicate_master_scan_ids == ()


def test_consistency_report_identifies_a_master_record_missing_for_session_observation(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "recording-data"
    finalize_session(data_dir, FIRST_SESSION_ID, [1, 2])
    append_master_records(data_dir, FIRST_SESSION_ID, [1])

    report = inspect_storage_consistency(data_dir)
    comparison = report.sessions[0]

    assert report.is_consistent is False
    assert comparison.missing_from_master == (2,)
    assert comparison.missing_from_session == ()
    assert comparison.master_record_count == 1


def test_consistency_report_identifies_duplicate_master_scan_ids(tmp_path: Path) -> None:
    data_dir = tmp_path / "recording-data"
    finalize_session(data_dir, FIRST_SESSION_ID, [1])
    master_path = data_dir / "master.jsonl"
    record = MasterScanRecord(session_id=FIRST_SESSION_ID, **build_observation(1).model_dump())
    master_path.write_text(
        f"{record.model_dump_json()}\n{record.model_dump_json()}\n",
        encoding="utf-8",
        newline="\n",
    )

    report = inspect_storage_consistency(data_dir)
    comparison = report.sessions[0]

    assert report.is_consistent is False
    assert comparison.master_record_count == 2
    assert comparison.duplicate_master_scan_ids == (1,)
    assert comparison.missing_from_master == ()
    assert comparison.missing_from_session == ()


def test_consistency_report_identifies_orphaned_master_records_without_session_file(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "recording-data"
    append_master_records(data_dir, SECOND_SESSION_ID, [1])

    report = inspect_storage_consistency(data_dir)

    assert report.is_consistent is False
    assert len(report.sessions) == 1
    comparison = report.sessions[0]
    assert comparison.session_id == SECOND_SESSION_ID
    assert comparison.session_path is None
    assert comparison.session_declared_scan_count is None
    assert comparison.master_record_count == 1
    assert comparison.missing_from_session == (1,)


def test_consistency_report_identifies_session_count_and_duplicate_observation_problems(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "recording-data"
    session_path = finalize_session(data_dir, FIRST_SESSION_ID, [1])
    payload = session_path.read_text(encoding="utf-8")
    session_path.write_text(
        payload.replace('"scan_count":1', '"scan_count":2').replace(
            '"observations":[', '"observations":[{"recorded_at":"2026-11-18T18:30:05Z","scan_id":1,"networks":[]},'
        ),
        encoding="utf-8",
        newline="\n",
    )
    append_master_records(data_dir, FIRST_SESSION_ID, [1])

    report = inspect_storage_consistency(data_dir)
    comparison = report.sessions[0]

    assert report.is_consistent is False
    assert comparison.session_declared_scan_count == 2
    assert comparison.session_observation_count == 2
    assert comparison.duplicate_session_scan_ids == (1,)