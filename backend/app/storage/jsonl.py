"""Append-only writer for validated version-1 master scan records."""

from __future__ import annotations

import os
from pathlib import Path
from threading import Lock
from dataclasses import dataclass

from app.storage.models import MasterScanRecord
from app.storage.naming import MASTER_FILENAME


class DuplicateMasterScanRecordError(ValueError):
    """Raised when a writer receives the same session and scan ID twice."""


class MasterJsonlIntegrityError(ValueError):
    """Raised when a repair would omit malformed non-final master-file data."""


@dataclass(frozen=True)
class MasterJsonlIntegrityIssue:
    """One malformed or schema-invalid complete line in a master JSONL file."""

    line_number: int
    detail: str


@dataclass(frozen=True)
class MasterJsonlIntegrityReport:
    """Read-only integrity result for a master JSONL file."""

    path: Path
    exists: bool
    valid_record_count: int
    final_incomplete_line: bool
    issues: tuple[MasterJsonlIntegrityIssue, ...]

    @property
    def is_clean(self) -> bool:
        """Return whether every stored line is a complete valid master record."""

        return self.exists and not self.final_incomplete_line and not self.issues


class MasterJsonlWriter:
    """Append one validated master record per line without rewriting prior data.

    The destination directory and file are created lazily on the first accepted
    append. This writer is not connected to live monitoring until a later
    recording workflow explicitly owns and invokes it.
    """

    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / MASTER_FILENAME
        self._written_record_ids: set[tuple[str, int]] = set()
        self._lock = Lock()

    @property
    def path(self) -> Path:
        """Return the future or existing master file path without creating it."""

        return self._path

    def append(self, record: MasterScanRecord) -> None:
        """Append exactly one JSONL record, flush it, and reject in-process duplicates."""

        if not isinstance(record, MasterScanRecord):
            raise TypeError("MasterJsonlWriter accepts MasterScanRecord instances only.")

        record_id = (record.session_id, record.scan_id)
        serialized_record = f"{record.model_dump_json()}\n"
        with self._lock:
            if record_id in self._written_record_ids:
                raise DuplicateMasterScanRecordError(
                    f"Master record already written for session {record.session_id} "
                    f"and scan {record.scan_id}."
                )

            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8", newline="\n") as master_file:
                master_file.write(serialized_record)
                master_file.flush()
                os.fsync(master_file.fileno())

            self._written_record_ids.add(record_id)


def inspect_master_jsonl(path: Path) -> MasterJsonlIntegrityReport:
    """Inspect a master file without modifying it.

    An invalid final physical line without a newline is reported separately as
    recoverable crash truncation. Invalid complete lines, including an invalid
    final line ending with a newline, remain visible as integrity issues.
    """

    if not path.exists():
        return MasterJsonlIntegrityReport(
            path=path,
            exists=False,
            valid_record_count=0,
            final_incomplete_line=False,
            issues=(),
        )

    raw_lines = path.read_bytes().splitlines(keepends=True)
    valid_record_count = 0
    issues: list[MasterJsonlIntegrityIssue] = []
    final_incomplete_line = False

    for line_number, raw_line in enumerate(raw_lines, start=1):
        has_newline = raw_line.endswith((b"\n", b"\r"))
        is_final_line = line_number == len(raw_lines)
        try:
            MasterScanRecord.model_validate_json(raw_line)
        except Exception as error:
            if is_final_line and not has_newline:
                final_incomplete_line = True
            else:
                issues.append(MasterJsonlIntegrityIssue(line_number, str(error)))
        else:
            valid_record_count += 1

    return MasterJsonlIntegrityReport(
        path=path,
        exists=True,
        valid_record_count=valid_record_count,
        final_incomplete_line=final_incomplete_line,
        issues=tuple(issues),
    )


def repair_master_jsonl(
    source_path: Path,
    repaired_path: Path,
    *,
    allow_nonfinal_issues: bool = False,
) -> MasterJsonlIntegrityReport:
    """Copy complete valid records into a separate repaired master file.

    The source is never changed. By default, repair refuses to omit malformed
    complete lines; callers must explicitly opt in to that evidence-preserving
    but lossy operation with ``allow_nonfinal_issues=True``. A crash-truncated
    final line is omitted from the repaired copy.
    """

    if source_path == repaired_path:
        raise ValueError("The repaired master path must differ from the source path.")

    report = inspect_master_jsonl(source_path)
    if not report.exists:
        raise FileNotFoundError(source_path)
    if report.issues and not allow_nonfinal_issues:
        raise MasterJsonlIntegrityError(
            "Refusing to omit malformed complete lines; inspect the integrity report "
            "or explicitly allow non-final issues."
        )

    valid_lines = [
        raw_line
        for raw_line in source_path.read_bytes().splitlines(keepends=True)
        if _is_complete_valid_record_line(raw_line)
    ]
    repaired_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = repaired_path.with_name(f"{repaired_path.name}.tmp")
    with temporary_path.open("wb") as repaired_file:
        for raw_line in valid_lines:
            repaired_file.write(raw_line if raw_line.endswith(b"\n") else raw_line + b"\n")
        repaired_file.flush()
        os.fsync(repaired_file.fileno())
    temporary_path.replace(repaired_path)
    return report


def _is_complete_valid_record_line(raw_line: bytes) -> bool:
    try:
        MasterScanRecord.model_validate_json(raw_line)
    except Exception:
        return False
    return True