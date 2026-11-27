"""Recoverable temporary session-file writing for active recording sessions."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock

from app.storage.models import ScanObservation, SessionMetadata
from app.storage.naming import build_temporary_session_filename


SESSIONS_DIRECTORY_NAME = "sessions"


class DuplicateSessionScanError(ValueError):
    """Raised when an active session receives the same scan ID twice."""


class TemporarySessionWriter:
    """Persist each active-session snapshot as a recoverable ``.json.tmp`` file.

    The writer is explicitly constructed by a future recording workflow. It is
    intentionally not connected to live scanning, and it never removes its
    temporary file; finalization is the responsibility of AIRSCAN-3.3.2.
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

    def append(self, observation: ScanObservation) -> None:
        """Persist one observation and updated counters as a complete JSON snapshot."""

        if not isinstance(observation, ScanObservation):
            raise TypeError("TemporarySessionWriter accepts ScanObservation instances only.")

        with self._lock:
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

    def _write_initial_snapshot(self) -> None:
        payload = _session_payload(self._metadata, self._observations)
        serialized_payload = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        try:
            with self._path.open("x", encoding="utf-8", newline="\n") as session_file:
                session_file.write(serialized_payload)
                session_file.flush()
                os.fsync(session_file.fileno())
        except FileExistsError as error:
            raise FileExistsError(f"Temporary session file already exists: {self._path}") from error

    def _write_replacement_snapshot(
        self,
        metadata: SessionMetadata,
        observations: list[ScanObservation],
    ) -> None:
        payload = _session_payload(metadata, observations)
        serialized_payload = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        replacement_path = self._path.with_name(f"{self._path.name}.writing")
        with replacement_path.open("w", encoding="utf-8", newline="\n") as replacement_file:
            replacement_file.write(serialized_payload)
            replacement_file.flush()
            os.fsync(replacement_file.fileno())
        replacement_path.replace(self._path)


def _session_payload(
    metadata: SessionMetadata,
    observations: list[ScanObservation],
) -> dict[str, object]:
    return {
        **metadata.model_dump(mode="json"),
        "observations": [observation.model_dump(mode="json") for observation in observations],
    }