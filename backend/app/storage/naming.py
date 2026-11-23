"""Pure naming rules for version-1 AirScan recording artifacts.

The helpers in this module validate and format identifiers only. They never
create directories or files.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import uuid4


MASTER_FILENAME = "master.jsonl"
SESSION_FILE_EXTENSION = ".json"
TEMPORARY_SESSION_FILE_EXTENSION = ".json.tmp"
SESSION_ID_PATTERN = r"^[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}$"
_SESSION_ID_RE = re.compile(SESSION_ID_PATTERN)


def generate_session_id() -> str:
    """Return a collision-resistant lowercase UUID4 hexadecimal session ID."""

    return uuid4().hex


def build_session_filename(started_at: datetime, session_id: str) -> str:
    """Build the finalized UTC session filename without creating it.

    The format is ``YYYY-MM-DD_HH-MM-SS_<session-id>.json``. The complete
    session ID suffix prevents names from colliding for sessions started in the
    same second.
    """

    _require_utc_timestamp(started_at)
    _require_session_id(session_id)
    return f"{started_at:%Y-%m-%d_%H-%M-%S}_{session_id}{SESSION_FILE_EXTENSION}"


def build_temporary_session_filename(started_at: datetime, session_id: str) -> str:
    """Build the recoverable active-session filename without creating it."""

    return f"{build_session_filename(started_at, session_id)}.tmp"


def _require_utc_timestamp(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Session filename timestamps must include a UTC offset.")
    if value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError("Session filename timestamps must use the UTC offset.")


def _require_session_id(value: str) -> None:
    if not _SESSION_ID_RE.fullmatch(value):
        raise ValueError("Session ID must be a 32-character lowercase UUID4 hexadecimal value.")