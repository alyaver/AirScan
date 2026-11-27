# AirScan

AirScan is an ESP32-based Wi-Fi scanner intended to detect nearby wireless networks and transmit signal data to a local PC application for analysis.

## Current status

The repository contains ESP32 firmware that scans nearby Wi-Fi networks and
writes version-1 newline-delimited JSON messages to USB serial.

For the confirmed firmware baseline, current serial-output limitations, and
planned development boundary, see
[docs/current-development-baseline.md](docs/current-development-baseline.md).

The version-1 firmware-to-backend serial contract is defined in
[docs/serial-protocol.md](docs/serial-protocol.md).

The version-1 backend recording schemas are defined in
[docs/storage-schema.md](docs/storage-schema.md). These schemas do not enable
recording or persistent storage by themselves.

## Local application

The repository includes a FastAPI backend and React dashboard for local live
monitoring. The backend receives version-1 NDJSON scan messages from one ESP32
USB serial port, keeps the current connection and latest-scan state in memory,
and publishes it through REST and WebSocket endpoints. The dashboard receives
live updates through the Vite WebSocket proxy and displays serial/device state,
recording state, and nearby Wi-Fi networks.

Recording controls are not implemented. The backend includes opt-in master
JSONL and temporary-session writers for a later recording workflow, but live
monitoring never invokes them and does not create scan-data files.

## Run the local application

After completing the frontend and backend setup steps, start both development
servers from the repository root:

```powershell
cd C:\Users\alyav\AirScan
npm install
npm run dev
```

This starts the FastAPI backend at `http://127.0.0.1:8000` and the Vite
frontend at `http://127.0.0.1:5173`. Press `Ctrl+C` once to stop both servers.

The frontend server uses port `5173` with strict port binding. If startup
reports that the port is already in use, stop the existing Vite process before
running `npm run dev` again. The dashboard WebSocket connects to `/api/live`,
which Vite proxies to the backend at `127.0.0.1:8000`.

## Serial-port configuration

The backend lists locally detected serial devices at `GET /api/serial/ports`.
Set `AIRSCAN_SERIAL_PORT` to a Windows port such as `COM7` before running
`npm run dev`; the backend then opens that explicitly configured port
automatically at startup. For the current PowerShell session:

```powershell
$env:AIRSCAN_SERIAL_PORT = "COM7"
npm run dev
```

If no port is configured, the backend remains available without claiming a
device; choose and open one through `PUT /api/serial/connection` with
`{"port":"COM7"}`. If a configured port is unavailable or currently held by
another program, the backend remains running and reports the connection error.
The selected port uses `AIRSCAN_SERIAL_BAUD_RATE`, which defaults to `115200`.
The backend opens and owns one port only. Close PlatformIO Serial Monitor before
starting AirScan because it cannot share the same COM port. Its serial reader
validates and normalizes accepted version-1 protocol messages before publishing
live state.

The current device state is available from `GET /api/serial/state`. It reports
USB serial/device activity such as `CONNECTED_IDLE` or `CONNECTED_SCANNING`; it
does not claim that the ESP32 is associated with a Wi-Fi network. After an
unexpected serial error, the selected port is retained and can be retried with
`POST /api/serial/reconnect`.

`GET /api/device/status` adds parser and reader diagnostics to this state, and
`GET /api/scans/latest` returns the latest accepted terminal scan (normalized
network observations or its terminal scan error). These are process-memory
snapshots only; recording/session history is not implemented yet.

For the live dashboard, `GET /api/live` returns an immediate snapshot of the
connection state, latest network observations, most recent scan time, accepted
terminal scan count since the current serial connection, and any current error.
It never waits for a new scan and does not create data files.

`WS /api/live` sends the same current snapshot immediately, then broadcasts
`connection_state` and `scan_update` events. Each browser has a bounded event
queue, so a slow or disconnected browser cannot block serial ingestion or other
connected clients; it receives the newest available snapshot after it catches
up.

The dashboard connection component consumes `WS /api/live` and displays the
ESP32 USB serial/device state, selected port, and last message/scan times. It
explicitly does not represent Wi-Fi access-point association.

The dashboard also shows the networks from the latest completed scan, with
SSID, BSSID, RSSI, channel, encryption, and last-observed time. It keeps
different BSSIDs separate even when they advertise the same SSID, labels empty
SSIDs as hidden networks, and can sort the latest scan by RSSI or SSID.

Live monitoring and recording are separate. Recording is currently inactive and
not implemented: receiving or viewing live scans does not create the configured
data directory, a master dataset, or session files.

## Live-monitoring end-to-end checklist

For the physical Windows/ESP32 validation procedure, including connection-loss,
browser WebSocket, scan-table, error-state, and no-persistence checks, see
[docs/live-monitoring-checklist.md](docs/live-monitoring-checklist.md).
