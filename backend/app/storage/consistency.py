"""Read-only consistency reporting between master JSONL and finalized sessions."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from app.storage.jsonl import MasterJsonlIntegrityReport, inspect_master_jsonl
from app.storage.models import MasterScanRecord, ScanObservation, SessionMetadata
from app.storage.naming import MASTER_FILENAME
from app.storage.sessions import SESSIONS_DIRECTORY_NAME


@dataclass(frozen=True)
class SessionFileIssue:
    """A finalized session file that cannot safely participate in comparison."""

    path: Path
    detail: str


@dataclass(frozen=True)
class SessionConsistency:
    """Comparison details for one session ID found in either storage source."""

    session_id: str
    session_path: Path | None
    session_declared_scan_count: int | None
    session_observation_count: int
    master_record_count: int
    missing_from_master: tuple[int, ...]
    missing_from_session: tuple[int, ...]
    duplicate_session_scan_ids: tuple[int, ...]
    duplicate_master_scan_ids: tuple[int, ...]

    @property
    def has_issues(self) -> bool:
        """Return whether this session has any count, ID, or source mismatch."""

        return (
            self.session_path is None
            or self.session_declared_scan_count != self.session_observation_count
            or bool(self.missing_from_master)
            or bool(self.missing_from_session)
            or bool(self.duplicate_session_scan_ids)
            or bool(self.duplicate_master_scan_ids)
        )


@dataclass(frozen=True)
class StorageConsistencyReport:
    """Read-only master/session comparison suitable for troubleshooting."""

    master_path: Path
    master_integrity: MasterJsonlIntegrityReport
    session_file_issues: tuple[SessionFileIssue, ...]
    sessions: tuple[SessionConsistency, ...]

    @property
    def is_consistent(self) -> bool:
        """Return whether all readable sources agree without integrity issues."""

        return (
            self.master_integrity.is_clean
            and not self.session_file_issues
            and not any(session.has_issues for session in self.sessions)
        )


@dataclass(frozen=True)
class _LoadedSession:
    path: Path
    metadata: SessionMetadata
    observations: tuple[ScanObservation, ...]


def inspect_storage_consistency(data_dir: Path) -> StorageConsistencyReport:
    """Compare validated master records with finalized session-file observations.

    The function never creates, changes, or repairs files. Only ``*.json`` files
    beneath ``data_dir/sessions`` are considered finalized sessions; active
    ``.json.tmp`` recovery artifacts are intentionally excluded.
    """

    master_path = data_dir / MASTER_FILENAME
    master_integrity = inspect_master_jsonl(master_path)
    master_records = _load_valid_master_records(master_path)
    loaded_sessions, session_file_issues = _load_finalized_sessions(data_dir / SESSIONS_DIRECTORY_NAME)

    sessions_by_id: dict[str, _LoadedSession] = {}
    for session in loaded_sessions:
        if session.metadata.session_id in sessions_by_id:
            session_file_issues.append(
                SessionFileIssue(
                    session.path,
                    f"Duplicate finalized session ID {session.metadata.session_id}; "
                    f"also present in {sessions_by_id[session.metadata.session_id].path}.",
                )
            )
            continue
        sessions_by_id[session.metadata.session_id] = session

    master_by_id: dict[str, list[MasterScanRecord]] = defaultdict(list)
    for record in master_records:
        master_by_id[record.session_id].append(record)

    session_ids = sorted(set(sessions_by_id) | set(master_by_id))
    comparisons = tuple(
        _compare_session(
            session_id,
            sessions_by_id.get(session_id),
            master_by_id.get(session_id, []),
        )
        for session_id in session_ids
    )
    return StorageConsistencyReport(
        master_path=master_path,
        master_integrity=master_integrity,
        session_file_issues=tuple(session_file_issues),
        sessions=comparisons,
    )


def _load_valid_master_records(path: Path) -> list[MasterScanRecord]:
    if not path.exists():
        return []

    records: list[MasterScanRecord] = []
    for raw_line in path.read_bytes().splitlines(keepends=True):
        try:
            records.append(MasterScanRecord.model_validate_json(raw_line))
        except Exception:
            continue
    return records


def _load_finalized_sessions(directory: Path) -> tuple[list[_LoadedSession], list[SessionFileIssue]]:
    if not directory.exists():
        return [], []

    sessions: list[_LoadedSession] = []
    issues: list[SessionFileIssue] = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Session document must be a JSON object.")
            observations_payload = payload.pop("observations")
            if not isinstance(observations_payload, list):
                raise ValueError("Session observations must be a JSON array.")
            metadata = SessionMetadata.model_validate_json(json.dumps(payload))
            if metadata.status == "active":
                raise ValueError("Finalized session files must not have active status.")
            observations = tuple(
                ScanObservation.model_validate_json(json.dumps(observation))
                for observation in observations_payload
            )
        except Exception as error:
            issues.append(SessionFileIssue(path, str(error)))
        else:
            sessions.append(_LoadedSession(path, metadata, observations))
    return sessions, issues


def _compare_session(
    session_id: str,
    session: _LoadedSession | None,
    master_records: list[MasterScanRecord],
) -> SessionConsistency:
    session_scan_ids = [observation.scan_id for observation in session.observations] if session else []
    master_scan_ids = [record.scan_id for record in master_records]
    session_id_set = set(session_scan_ids)
    master_id_set = set(master_scan_ids)

    return SessionConsistency(
        session_id=session_id,
        session_path=session.path if session else None,
        session_declared_scan_count=session.metadata.scan_count if session else None,
        session_observation_count=len(session_scan_ids),
        master_record_count=len(master_scan_ids),
        missing_from_master=tuple(sorted(session_id_set - master_id_set)),
        missing_from_session=tuple(sorted(master_id_set - session_id_set)),
        duplicate_session_scan_ids=_duplicate_ids(session_scan_ids),
        duplicate_master_scan_ids=_duplicate_ids(master_scan_ids),
    )


def _duplicate_ids(scan_ids: list[int]) -> tuple[int, ...]:
    return tuple(sorted(scan_id for scan_id, count in Counter(scan_ids).items() if count > 1))