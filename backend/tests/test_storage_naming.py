from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.storage.naming import (
    MASTER_FILENAME,
    build_session_filename,
    build_temporary_session_filename,
    generate_session_id,
)


UTC_TIMESTAMP = datetime(2026, 11, 9, 19, 30, 0, tzinfo=timezone.utc)
SESSION_ID = "7f2a9c2183ce4fa79ebd7dbdc5f8e9a1"


def test_session_ids_are_unique_and_match_the_filename_safe_contract() -> None:
    session_ids = {generate_session_id() for _ in range(1_000)}

    assert len(session_ids) == 1_000
    assert all(len(session_id) == 32 and session_id.isalnum() and session_id.islower() for session_id in session_ids)


def test_session_filenames_use_utc_timestamp_and_session_id_to_prevent_collisions() -> None:
    first_filename = build_session_filename(UTC_TIMESTAMP, SESSION_ID)
    second_filename = build_session_filename(
        UTC_TIMESTAMP,
        "d4ea7b4187ed411eacbbf9e72c2a4d51",
    )

    assert MASTER_FILENAME == "master.jsonl"
    assert first_filename == "2026-11-09_19-30-00_7f2a9c2183ce4fa79ebd7dbdc5f8e9a1.json"
    assert first_filename != second_filename
    assert build_temporary_session_filename(UTC_TIMESTAMP, SESSION_ID) == f"{first_filename}.tmp"


@pytest.mark.parametrize(
    ("started_at", "session_id"),
    [
        (datetime(2026, 11, 9, 19, 30, 0), SESSION_ID),
        (UTC_TIMESTAMP.astimezone(timezone(timedelta(hours=-5))), SESSION_ID),
        (UTC_TIMESTAMP, "session-123"),
        (UTC_TIMESTAMP, "7F2A9C2183CE4FA79EBD7DBDC5F8E9A1"),
    ],
)
def test_session_filenames_reject_ambiguous_timestamps_and_unsafe_ids(
    started_at: datetime,
    session_id: str,
) -> None:
    with pytest.raises(ValueError):
        build_session_filename(started_at, session_id)