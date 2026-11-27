from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.storage.models import ScanObservation, SessionMetadata
from app.storage.sessions import (
    DuplicateSessionScanError,
    SessionAlreadyFinalizedError,
    TemporarySessionWriter,
)


UTC_TIMESTAMP = datetime(2026, 11, 18, 18, 30, 5, 142000, tzinfo=timezone.utc)
SESSION_ID = "7f2a9c2183ce4fa79ebd7dbdc5f8e9a1"


def build_metadata() -> SessionMetadata:
    return SessionMetadata(
        session_id=SESSION_ID,
        label="Baseline",
        notes="Temporary recording.",
        started_at=UTC_TIMESTAMP,
        status="active",
    )


def build_observation(scan_id: int, bssids: list[str]) -> ScanObservation:
    return ScanObservation(
        recorded_at=UTC_TIMESTAMP,
        scan_id=scan_id,
        networks=[
            {
                "ssid": f"Network {index}",
                "bssid": bssid,
                "rssi_dbm": -50,
                "channel": 6,
                "encryption": "Encrypted",
            }
            for index, bssid in enumerate(bssids, start=1)
        ],
    )


def read_session_payload(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_session_start_creates_a_distinguishable_recoverable_empty_temporary_file(
    tmp_path: Path,
) -> None:
    metadata = build_metadata()
    writer = TemporarySessionWriter(tmp_path / "recording-data", metadata)

    assert writer.path.parent == tmp_path / "recording-data" / "sessions"
    assert writer.path.name == "2026-11-18_18-30-05_7f2a9c2183ce4fa79ebd7dbdc5f8e9a1.json.tmp"
    assert writer.path.exists()
    assert read_session_payload(writer.path) == {
        **metadata.model_dump(mode="json"),
        "observations": [],
    }


def test_session_writer_persists_observations_and_derived_counters_after_each_append(
    tmp_path: Path,
) -> None:
    writer = TemporarySessionWriter(tmp_path / "recording-data", build_metadata())
    first_observation = build_observation(1, ["aa:bb:cc:dd:ee:ff"])
    second_observation = build_observation(
        2,
        ["aa:bb:cc:dd:ee:ff", "11:22:33:44:55:66"],
    )

    writer.append(first_observation)
    first_payload = read_session_payload(writer.path)
    writer.append(second_observation)
    second_payload = read_session_payload(writer.path)

    assert first_payload["scan_count"] == 1
    assert first_payload["unique_bssid_count"] == 1
    assert first_payload["observations"] == [first_observation.model_dump(mode="json")]
    assert second_payload["scan_count"] == 2
    assert second_payload["unique_bssid_count"] == 2
    assert second_payload["observations"] == [
        first_observation.model_dump(mode="json"),
        second_observation.model_dump(mode="json"),
    ]
    assert writer.metadata.scan_count == 2
    assert writer.metadata.unique_bssid_count == 2
    assert writer.path.with_name(f"{writer.path.name}.writing").exists() is False


def test_session_writer_rejects_duplicate_scan_ids_without_replacing_recoverable_file(
    tmp_path: Path,
) -> None:
    writer = TemporarySessionWriter(tmp_path / "recording-data", build_metadata())
    observation = build_observation(1, ["aa:bb:cc:dd:ee:ff"])
    writer.append(observation)
    persisted_payload = writer.path.read_bytes()

    with pytest.raises(DuplicateSessionScanError, match="already been written"):
        writer.append(observation)

    assert writer.path.read_bytes() == persisted_payload


def test_session_writer_preserves_temporary_file_when_writer_is_discarded(tmp_path: Path) -> None:
    writer = TemporarySessionWriter(tmp_path / "recording-data", build_metadata())
    writer.append(build_observation(1, ["aa:bb:cc:dd:ee:ff"]))
    path = writer.path

    del writer

    assert path.exists()
    assert read_session_payload(path)["scan_count"] == 1


def test_session_writer_requires_active_metadata_and_validated_observations(tmp_path: Path) -> None:
    finalized_metadata = build_metadata().model_copy(
        update={
            "status": "completed",
            "ended_at": UTC_TIMESTAMP,
            "duration_seconds": 0,
        }
    )

    with pytest.raises(ValueError, match="active"):
        TemporarySessionWriter(tmp_path / "recording-data", finalized_metadata)

    writer = TemporarySessionWriter(tmp_path / "another-recording-data", build_metadata())
    with pytest.raises(TypeError, match="ScanObservation"):
        writer.append(object())  # type: ignore[arg-type]
    assert read_session_payload(writer.path)["observations"] == []


def test_finalize_empty_session_publishes_complete_json_and_removes_temporary_file(tmp_path: Path) -> None:
    writer = TemporarySessionWriter(tmp_path / "recording-data", build_metadata())
    temporary_path = writer.path
    ended_at = datetime(2026, 11, 18, 18, 31, 10, tzinfo=timezone.utc)

    finalized_path = writer.finalize(ended_at)

    assert finalized_path == (
        tmp_path
        / "recording-data"
        / "sessions"
        / "2026-11-18_18-30-05_7f2a9c2183ce4fa79ebd7dbdc5f8e9a1.json"
    )
    assert temporary_path.exists() is False
    assert finalized_path.exists()
    assert read_session_payload(finalized_path) == {
        **build_metadata().model_dump(mode="json"),
        "ended_at": "2026-11-18T18:31:10Z",
        "duration_seconds": 64,
        "scan_count": 0,
        "unique_bssid_count": 0,
        "status": "completed",
        "observations": [],
    }
    assert writer.metadata.status == "completed"
    assert writer.finalized_path == finalized_path


def test_finalize_multiple_scans_calculates_counts_and_prevents_further_mutation(tmp_path: Path) -> None:
    writer = TemporarySessionWriter(tmp_path / "recording-data", build_metadata())
    first_observation = build_observation(1, ["aa:bb:cc:dd:ee:ff"])
    second_observation = build_observation(
        2,
        ["aa:bb:cc:dd:ee:ff", "11:22:33:44:55:66"],
    )
    writer.append(first_observation)
    writer.append(second_observation)

    finalized_path = writer.finalize(datetime(2026, 11, 18, 18, 32, 5, tzinfo=timezone.utc))
    payload = read_session_payload(finalized_path)

    assert payload["duration_seconds"] == 119
    assert payload["scan_count"] == 2
    assert payload["unique_bssid_count"] == 2
    assert payload["observations"] == [
        first_observation.model_dump(mode="json"),
        second_observation.model_dump(mode="json"),
    ]
    with pytest.raises(SessionAlreadyFinalizedError, match="already been finalized"):
        writer.append(build_observation(3, ["22:33:44:55:66:77"]))
    with pytest.raises(SessionAlreadyFinalizedError, match="already been finalized"):
        writer.finalize(datetime(2026, 11, 18, 18, 33, 5, tzinfo=timezone.utc))


def test_finalization_failure_preserves_the_existing_recoverable_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = TemporarySessionWriter(tmp_path / "recording-data", build_metadata())
    writer.append(build_observation(1, ["aa:bb:cc:dd:ee:ff"]))
    temporary_payload = writer.path.read_bytes()

    def fail_publish(self: Path, target: Path) -> Path:
        raise OSError("simulated final publication failure")

    monkeypatch.setattr(Path, "replace", fail_publish)

    with pytest.raises(OSError, match="simulated final publication failure"):
        writer.finalize(datetime(2026, 11, 18, 18, 32, 5, tzinfo=timezone.utc))

    assert writer.path.exists()
    assert writer.path.read_bytes() == temporary_payload
    assert writer.finalized_path is None
    assert list(writer.path.parent.glob("*.json.writing")) == []