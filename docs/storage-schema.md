# AirScan Storage Schema, Version 1

## Status and scope

This document defines the canonical backend models introduced by
`AIRSCAN-3.1.1`. They validate version-1 recording payloads but do not create
files or enable recording. Live monitoring therefore remains memory-only until
a later recording task explicitly invokes a storage writer.

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
  "session_id": "session-123",
  "recorded_at": "2026-11-18T18:30:05.142000Z",
  "scan_id": 42,
  "networks": []
}
```

Each record includes the same scan fields and network structure as
`ScanObservation`, plus a non-empty `session_id` for provenance.

## Session metadata

`SessionMetadata` is the shared metadata portion of temporary and finalized
session files:

| Field | Rule |
| --- | --- |
| `schema_version` | Always `1`. |
| `session_id` | Non-empty stable session identifier. |
| `label` | Non-empty user-facing label. Permitted initial labels are defined by AIRSCAN-3.1.2. |
| `notes` | Optional text; defaults to an empty string. |
| `started_at` | Required backend UTC timestamp. |
| `ended_at` | Optional backend UTC timestamp. |
| `duration_seconds` | Optional non-negative integer. |
| `scan_count` | Non-negative integer, initially zero. |
| `unique_bssid_count` | Non-negative integer, initially zero. |
| `status` | `active`, `completed`, `interrupted`, or `recovered`. |

Session files will pair this metadata with an array of `ScanObservation` values.

## Recovery status

`RecoveryStatus` is a schema-versioned record for temporary-session recovery:

| Field | Rule |
| --- | --- |
| `schema_version` | Always `1`. |
| `session_id` | Non-empty session identifier. |
| `status` | `pending`, `recovered`, or `discarded`. |
| `detected_at` | Required backend UTC timestamp. |
| `detail` | Optional diagnostic text. |

Later storage tasks determine where recovery records live and how they are
created; this task only establishes their validated format.