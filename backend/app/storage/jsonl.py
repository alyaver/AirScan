"""Append-only writer for validated version-1 master scan records."""

from __future__ import annotations

import os
from pathlib import Path
from threading import Lock

from app.storage.models import MasterScanRecord
from app.storage.naming import MASTER_FILENAME


class DuplicateMasterScanRecordError(ValueError):
    """Raised when a writer receives the same session and scan ID twice."""


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