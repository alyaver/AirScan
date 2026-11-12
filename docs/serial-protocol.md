# AirScan Serial Protocol

## Purpose and status

This document defines version 1 of the USB-serial protocol from the AirScan
ESP32 firmware to the local backend. Firmware task `AIRSCAN-1.2.2` implements
the `device_ready`, `scan_result`, and `scan_error` messages defined here.

Version 1 replaces display-oriented serial output with machine-readable
messages while retaining SSID, BSSID, RSSI, channel, and the current `Open` or
`Encrypted` classification.

## Transport and framing

| Property | Version 1 rule |
| --- | --- |
| Transport | USB serial |
| Baud rate | `115200` baud |
| Text encoding | UTF-8 |
| Framing | Newline-delimited JSON (NDJSON) |
| Line ending | Firmware emits `\n`; backend accepts `\n` or `\r\n` |
| Record boundary | One complete JSON object per non-empty line |
| Direction | ESP32 firmware to local backend |

The application serial stream must contain no human-readable status or
diagnostic text. JSON string escaping must preserve quotes, backslashes,
control characters, and newlines in values such as SSIDs without changing line
framing.

## Common message envelope

Every message is a JSON object with these required fields:

| Field | Type | Rule |
| --- | --- | --- |
| `protocol_version` | integer | Must equal `1`. |
| `message_type` | string | Must be a supported version-1 type. |
| `device_timestamp_ms` | integer | Non-negative elapsed milliseconds since this firmware boot. This is diagnostic metadata, not wall-clock time. |

Supported message types are `device_ready`, `heartbeat`, `scan_result`,
`scan_error`, and `device_error`.

## Message schemas

### `device_ready`

The firmware emits this once after serial and Wi-Fi scan initialization are
ready, and again after each device reset.

| Additional field | Type | Rule |
| --- | --- | --- |
| `device_id` | string | Non-empty stable identifier when available. Version 1 permits `"esp32-unknown"`. |
| `firmware_version` | string | Non-empty firmware version. |

```json
{"protocol_version":1,"message_type":"device_ready","device_id":"esp32-unknown","firmware_version":"0.1.0","device_timestamp_ms":1042}
```

### `heartbeat`

The firmware may emit this periodically while responsive. It is not a scan
result and does not create an observation or advance a scan ID. It is reserved
in version 1 even if periodic heartbeats are implemented later.

| Additional field | Type | Rule |
| --- | --- | --- |
| `scan_in_progress` | boolean | `true` while a Wi-Fi scan is active; otherwise `false`. |

```json
{"protocol_version":1,"message_type":"heartbeat","device_timestamp_ms":10000,"scan_in_progress":false}
```

### `scan_result`

The firmware emits exactly one `scan_result` after each successful completed
`WiFi.scanNetworks()` call. A successful scan with no discovered networks is
valid and uses `[]` for `networks`.

| Additional field | Type | Rule |
| --- | --- | --- |
| `scan_id` | integer | Positive and monotonically increasing during the current firmware boot. |
| `networks` | array | Zero or more network objects. |

Every network object contains:

| Field | Type | Rule |
| --- | --- | --- |
| `ssid` | string | May be empty for a hidden SSID. |
| `bssid` | string | Uppercase colon-separated MAC address, such as `AA:BB:CC:DD:EE:FF`. |
| `rssi_dbm` | integer | Received signal strength in dBm. Negative values are expected. |
| `channel` | integer | Positive channel number reported by the ESP32. |
| `encryption` | string | Exactly `Open` or `Encrypted`. |

```json
{"protocol_version":1,"message_type":"scan_result","scan_id":42,"device_timestamp_ms":123456,"networks":[{"ssid":"example-network","bssid":"AA:BB:CC:DD:EE:FF","rssi_dbm":-52,"channel":6,"encryption":"Encrypted"}]}
```

```json
{"protocol_version":1,"message_type":"scan_result","scan_id":43,"device_timestamp_ms":129000,"networks":[]}
```

### `scan_error`

The firmware emits this when a scan attempt fails. The failed attempt consumes
a `scan_id`, allowing the backend to distinguish a known failure from a missing
message.

| Additional field | Type | Rule |
| --- | --- | --- |
| `scan_id` | integer | Positive and monotonically increasing during the current firmware boot. |
| `error_code` | string | Stable machine-readable identifier; use `wifi_scan_failed` for a negative `WiFi.scanNetworks()` result. |
| `message` | string | Non-empty human-readable diagnostic. |

```json
{"protocol_version":1,"message_type":"scan_error","scan_id":44,"device_timestamp_ms":134000,"error_code":"wifi_scan_failed","message":"WiFi.scanNetworks returned -1."}
```

### `device_error`

The firmware emits this for a device-level error that is not tied to one scan.
It must not contain `scan_id` in version 1.

| Additional field | Type | Rule |
| --- | --- | --- |
| `error_code` | string | Stable machine-readable identifier. |
| `message` | string | Non-empty human-readable diagnostic. |

```json
{"protocol_version":1,"message_type":"device_error","device_timestamp_ms":135000,"error_code":"wifi_initialization_failed","message":"Wi-Fi station mode could not be initialized."}
```

## Scan ID and timestamp rules

- Initialize `scan_id` to a positive value after firmware boot.
- Increment it exactly once per scan attempt, whether the terminal message is
  `scan_result` or `scan_error`.
- Do not emit more than one terminal scan message for the same ID.
- IDs and device timestamps may restart after reset; `device_ready` marks the
  new firmware-session boundary.
- The backend accepts a completed scan ID at most once per firmware session and
  safely ignores or rejects duplicates.
- The backend receipt time is authoritative for live display and later
  recording chronology; `device_timestamp_ms` is retained as diagnostic data.

## Firmware scan scheduling

Version-1 firmware uses a minimum **start-to-start** scan interval of five
seconds. It records the start time immediately before each blocking
`WiFi.scanNetworks()` call and does not begin another scan until at least five
seconds have elapsed from that time.

The scan call is blocking, and firmware also maintains an explicit
`scanInProgress` guard. Together, these rules ensure that only one scan can be
active, terminal scan messages cannot be interleaved, and scan IDs are emitted
in order. If a scan takes longer than five seconds, the next scan becomes
eligible immediately after the completed result or error message is emitted and
`WiFi.scanDelete()` releases the scan results.

## Backend validation and error handling

For each complete non-empty line, the backend must:

1. Decode UTF-8 and parse exactly one JSON object.
2. Check `protocol_version` before message-specific parsing.
3. Validate the common envelope and selected message schema.
4. Normalize accepted networks: uppercase colon-separated BSSID, integer RSSI
   and channel, and `Open` or `Encrypted` encryption.
5. Count, log, and ignore malformed or invalid messages without stopping serial
   reading.

A serial reader must continue after malformed JSON, decode errors, timeouts,
invalid fields, duplicate scan IDs, or unknown message types.

- A protocol version other than `1` is logged and ignored without version-1
  parsing.
- An unknown version-1 `message_type` is logged and ignored.
- Unknown extra fields on an otherwise valid version-1 message are allowed and
  ignored for forward compatibility.

## Invalid examples

The backend must reject these lines safely:

Missing protocol version:

```json
{"message_type":"heartbeat","device_timestamp_ms":10000,"scan_in_progress":false}
```

Malformed JSON:

```text
{"protocol_version":1,"message_type":"heartbeat"
```

Invalid BSSID format:

```json
{"protocol_version":1,"message_type":"scan_result","scan_id":45,"device_timestamp_ms":140000,"networks":[{"ssid":"example-network","bssid":"AA-BB-CC-DD-EE-FF","rssi_dbm":-52,"channel":6,"encryption":"Encrypted"}]}
```

Unsupported encryption classification:

```json
{"protocol_version":1,"message_type":"scan_result","scan_id":46,"device_timestamp_ms":145000,"networks":[{"ssid":"example-network","bssid":"AA:BB:CC:DD:EE:FF","rssi_dbm":-52,"channel":6,"encryption":"WPA3"}]}
```

## Compatibility and implementation boundary

This document defines the protocol and its firmware implementation boundary. It
does not add a serial reader to the backend or define storage records. The
firmware retains `WiFi.scanNetworks()` and emits one terminal scan message
before calling `WiFi.scanDelete()`.

An incompatible protocol change requires a new `protocol_version` and updated
firmware/backend support. Version 1 may add optional fields because receivers
ignore unknown fields.