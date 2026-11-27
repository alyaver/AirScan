# AirScan Storage Schema, Version 1

## Status and scope

This document defines the canonical backend models and session naming contract
introduced by `AIRSCAN-3.1.1` and `AIRSCAN-3.1.2`. They validate version-1
recording payloads and format future artifact names, but do not create files or
enable recording. Live monitoring therefore remains memory-only until a later
recording task explicitly invokes a storage writer.

All timestamps are timezone-aware UTC datetimes serialized as ISO 8601 strings
with a `Z` suffix. All storage models are strict and reject unknown fields.

## Canonical network structure

Every network in live state, a scan observation, a session file, and a master
JSONL record uses this exact normalized shape:

| Field | Type | Rule |
| --- | --- | --- |
| `ssid` | string | May be empty for a hidden network. |
| `bssid` | string | Colon-separated six-octet MAC address; normalized to uppercase. |
| `rssi_dbm` | integer | Signal strength in dBm. |
| `channel` | positive integer | Channel reported by the ESP32. |
| `encryption` | string | `Open` or `Encrypted`. |

The backend uses `NetworkObservation` from the serial protocol as this shared
canonical structure, so stored and live records have identical normalization.

## Scan observation

`ScanObservation` represents one accepted successful completed scan:

```json
{
  "recorded_at": "2026-11-18T18:30:05.142000Z",
  "scan_id": 42,
  "networks": [
    {
      "ssid": "example-network",
      "bssid": "AA:BB:CC:DD:EE:FF",
      "rssi_dbm": -52,
      "channel": 6,
      "encryption": "Encrypted"
    }
  ]
}
```

`recorded_at` is assigned by the backend, rather than copied from the
firmware's elapsed-millisecond diagnostic timestamp. `scan_id` is positive and
`networks` may be empty for a valid empty scan.

## Master JSONL record

`MasterScanRecord` is the one-line record planned for `master.jsonl`:

```json
{
  "record_type": "scan",
  "schema_version": 1,
  "session_id": "7f2a9c2183ce4fa79ebd7dbdc5f8e9a1",
  "recorded_at": "2026-11-18T18:30:05.142000Z",
  "scan_id": 42,
  "networks": []
}
```

Each record includes the same scan fields and network structure as
`ScanObservation`, plus its canonical UUID4 `session_id` for provenance.

## Session metadata

`SessionMetadata` is the shared metadata portion of temporary and finalized
session files:

| Field | Rule |
| --- | --- |
| `schema_version` | Always `1`. |
| `session_id` | Stable 32-character lowercase UUID4 hexadecimal identifier. |
| `label` | One of `Police Observed`, `Baseline`, or `Unknown`. |
| `notes` | Optional user text; defaults to an empty string and is stored separately from the filename. |
| `started_at` | Required backend UTC timestamp. |
| `ended_at` | Optional backend UTC timestamp. |
| `duration_seconds` | Optional non-negative integer. |
| `scan_count` | Non-negative integer, initially zero. |
| `unique_bssid_count` | Non-negative integer, initially zero. |
| `status` | `active`, `completed`, `interrupted`, or `recovered`. Active sessions have no end time or duration; every other status requires both. |

Session files will pair this metadata with an array of `ScanObservation` values.

## Temporary active session files

`TemporarySessionWriter` is the explicit storage component for an active
recording session. Given active `SessionMetadata`, it creates one recoverable
file under `data/sessions/` using the documented `.json.tmp` filename format.
The file is a complete JSON object with the metadata fields at the top level and
an `observations` array of canonical `ScanObservation` values.

The writer persists an empty active-session snapshot at construction. Each
accepted append rewrites a complete replacement snapshot, flushes and
synchronizes it, then replaces the active `.json.tmp` file. The snapshot updates
`scan_count` and `unique_bssid_count` from the persisted observations. A
duplicate scan ID is rejected for the active writer, and the existing temporary
file remains unchanged.

Temporary files are intentionally retained when the writer stops unexpectedly.
No live-monitoring code constructs this writer yet, so running the application
without a future recording workflow still creates no session files.

Calling `TemporarySessionWriter.finalize()` creates finalized metadata with an
end timestamp, elapsed whole-second duration, persisted scan count, unique BSSID
count, and final status (normally `completed`). It first writes and synchronizes
a separate replacement for the completed `.json` filename, then atomically
publishes that file. Only after publication succeeds does it remove the
recoverable `.json.tmp` file. A failure before publication leaves the active
temporary file available for recovery.

## Session identity and filenames

The backend generates each session ID as a lowercase UUID4 hexadecimal value,
for example `7f2a9c2183ce4fa79ebd7dbdc5f8e9a1`. UUID4 generation gives each
session a stable, collision-resistant identity independent of its label.

Session filenames use the session start time in UTC and never use the label or
notes, so user-entered text cannot affect paths. The finalized filename grammar
is:

```text
YYYY-MM-DD_HH-MM-SS_<session-id>.json
```

For example:

```text
2026-11-09_19-30-00_7f2a9c2183ce4fa79ebd7dbdc5f8e9a1.json
```

The full session-ID suffix prevents collisions when multiple sessions begin in
the same second. Active, recoverable session files use the same base name with
an additional `.tmp` suffix:

```text
2026-11-09_19-30-00_7f2a9c2183ce4fa79ebd7dbdc5f8e9a1.json.tmp
```

`master.jsonl` is the reserved future master-dataset filename. Naming helpers
only return strings; they do not create the master or session files.

## Master JSONL append contract

`MasterJsonlWriter` is the explicit storage component for future recording
workflows. It accepts only validated `MasterScanRecord` instances and appends
their canonical JSON representation followed by one newline to
`data/master.jsonl` (or the configured data directory).

- Constructing the writer does not create a directory or file.
- The data directory and `master.jsonl` are created only by the first accepted
  `append` call.
- Every append flushes and synchronizes the complete line before returning.
- Existing master-file content is never rewritten by normal appends.
- A writer instance rejects a repeated `(session_id, scan_id)` pair.
- The writer is intentionally not connected to live scan processing yet;
  running live monitoring alone still does not create scan-data files.

Validation of pre-existing duplicate master records is deferred to a later
consistency-reporting task.

## Master JSONL integrity and recovery

`inspect_master_jsonl` reads a master file without changing it. It validates
every complete physical line as a `MasterScanRecord` and returns the count of
valid records plus line-numbered issues for malformed or schema-invalid lines.

An invalid final line that does not end with a newline is reported separately as
`final_incomplete_line`, which represents a recoverable crash-truncation case.
It is not treated as evidence that a prior complete record is invalid.

`repair_master_jsonl` always writes to a separate destination and never modifies
the source. It copies complete valid records to the repaired file and omits an
incomplete final line. By default, it refuses to omit malformed complete lines;
callers must explicitly set `allow_nonfinal_issues=True` after reviewing the
integrity report. This preserves the original file as evidence and prevents
silent loss of non-final malformed data.

## Recovery status

`RecoveryStatus` is a schema-versioned record for temporary-session recovery:

| Field | Rule |
| --- | --- |
| `schema_version` | Always `1`. |
| `session_id` | Stable 32-character lowercase UUID4 hexadecimal identifier. |
| `status` | `pending`, `recovered`, or `discarded`. |
| `detected_at` | Required backend UTC timestamp. |
| `detail` | Optional diagnostic text. |

Later storage tasks determine where recovery records live and how they are
created; this task only establishes their validated format.