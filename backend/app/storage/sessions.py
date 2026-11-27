"""Recoverable temporary session-file writing for active recording sessions."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Literal

from app.storage.models import ScanObservation, SessionMetadata
from app.storage.naming import build_session_filename, build_temporary_session_filename


SESSIONS_DIRECTORY_NAME = "sessions"


class DuplicateSessionScanError(ValueError):
    """Raised when an active session receives the same scan ID twice."""


class SessionAlreadyFinalizedError(ValueError):
    """Raised when an operation attempts to change a finalized session."""


class TemporarySessionWriter:
    """Persist each active-session snapshot as a recoverable ``.json.tmp`` file.

    The writer is explicitly constructed by a future recording workflow. It is
    intentionally not connected to live scanning. Finalization writes and
    publishes a complete ``.json`` session only after its replacement file is
    durable, preserving the active temporary file if that operation fails.
    """

    def __init__(self, data_dir: Path, metadata: SessionMetadata) -> None:
        if metadata.status != "active":
            raise ValueError("Temporary sessions require active session metadata.")

        self._path = (
            data_dir
            / SESSIONS_DIRECTORY_NAME
            / build_temporary_session_filename(metadata.started_at, metadata.session_id)
        )
        self._metadata = metadata
        self._observations: list[ScanObservation] = []
        self._scan_ids: set[int] = set()
        self._bssids: set[str] = set()
        self._finalized_path: Path | None = None
        self._lock = Lock()

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._write_initial_snapshot()

    @property
    def path(self) -> Path:
        """Return the active temporary session path."""

        return self._path

    @property
    def metadata(self) -> SessionMetadata:
        """Return current active metadata and derived counters."""

        with self._lock:
            return self._metadata

    @property
    def finalized_path(self) -> Path | None:
        """Return the completed session path after successful finalization."""

        with self._lock:
            return self._finalized_path

    def append(self, observation: ScanObservation) -> None:
        """Persist one observation and updated counters as a complete JSON snapshot."""

        if not isinstance(observation, ScanObservation):
            raise TypeError("TemporarySessionWriter accepts ScanObservation instances only.")

        with self._lock:
            self._require_active()
            if observation.scan_id in self._scan_ids:
                raise DuplicateSessionScanError(
                    f"Session scan {observation.scan_id} has already been written."
                )

            observations = [*self._observations, observation]
            bssids = {
                network.bssid
                for scan_observation in observations
                for network in scan_observation.networks
            }
            metadata = self._metadata.model_copy(
                update={
                    "scan_count": len(observations),
                    "unique_bssid_count": len(bssids),
                }
            )
            self._write_replacement_snapshot(metadata, observations)

            self._metadata = metadata
            self._observations = observations
            self._scan_ids.add(observation.scan_id)
            self._bssids = bssids

    def finalize(
        self,
        ended_at: datetime,
        *,
        status: Literal["completed", "interrupted", "recovered"] = "completed",
    ) -> Path:
        """Atomically publish the session's durable finalized ``.json`` file.

        The active ``.json.tmp`` file remains the recovery source until the
        complete final replacement has been flushed, synchronized, and atomically
        published. It is deleted only after that publication succeeds.
        """

        with self._lock:
            self._require_active()
            metadata = SessionMetadata.model_validate(
                self._metadata.model_dump()
                | {
                    "ended_at": ended_at,
                    "duration_seconds": int(
                        (ended_at - self._metadata.started_at).total_seconds()
                    ),
                    "scan_count": len(self._observations),
                    "unique_bssid_count": len(self._bssids),
                    "status": status,
                }
            )
            finalized_path = self._path.with_name(
                build_session_filename(metadata.started_at, metadata.session_id)
            )
            replacement_path = finalized_path.with_name(f"{finalized_path.name}.writing")

            self._write_snapshot(replacement_path, metadata, self._observations, exclusive=True)
            try:
                replacement_path.replace(finalized_path)
            except Exception:
                replacement_path.unlink(missing_ok=True)
                raise

            self._path.unlink()
            self._metadata = metadata
            self._finalized_path = finalized_path
            return finalized_path

    def _write_initial_snapshot(self) -> None:
        try:
            self._write_snapshot(self._path, self._metadata, self._observations, exclusive=True)
        except FileExistsError as error:
            raise FileExistsError(f"Temporary session file already exists: {self._path}") from error

    def _write_replacement_snapshot(
        self,
        metadata: SessionMetadata,
        observations: list[ScanObservation],
    ) -> None:
        replacement_path = self._path.with_name(f"{self._path.name}.writing")
        self._write_snapshot(replacement_path, metadata, observations)
        replacement_path.replace(self._path)

    def _write_snapshot(
        self,
        path: Path,
        metadata: SessionMetadata,
        observations: list[ScanObservation],
        *,
        exclusive: bool = False,
    ) -> None:
        payload = _session_payload(metadata, observations)
        serialized_payload = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        mode = "x" if exclusive else "w"
        with path.open(mode, encoding="utf-8", newline="\n") as replacement_file:
            replacement_file.write(serialized_payload)
            replacement_file.flush()
            os.fsync(replacement_file.fileno())

    def _require_active(self) -> None:
        if self._finalized_path is not None:
            raise SessionAlreadyFinalizedError("This session has already been finalized.")


def _session_payload(
    metadata: SessionMetadata,
    observations: list[ScanObservation],
) -> dict[str, object]:
    return {
        **metadata.model_dump(mode="json"),
        "observations": [observation.model_dump(mode="json") for observation in observations],
    }