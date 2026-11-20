# AirScan Live-Monitoring End-to-End Checklist

Use this checklist to validate the Phase 2 live-monitoring milestone with a
physical ESP32 on Windows. It verifies the complete path without enabling
recording:

```text
ESP32 NDJSON USB serial -> FastAPI -> WS /api/live -> Vite proxy -> browser
```

## Preconditions

1. Flash firmware that implements the version-1 serial protocol documented in
   [serial-protocol.md](serial-protocol.md).
2. Connect the ESP32 by USB and identify its Windows COM port, for example
   `COM8`.
3. Close the PlatformIO serial monitor and every other program that could own
   the COM port. The FastAPI backend must be the only serial-port owner.
4. From the repository root, ensure dependencies have been installed:

   ```powershell
   cd C:\Users\alyav\AirScan
   npm install
   ```

## Start the local application

1. Start both services:

   ```powershell
   npm run dev
   ```

2. Confirm the backend is reachable:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8000/api/health
   ```

   Expected: a response identifying the AirScan service with status `ok`.

3. Open `http://127.0.0.1:5173` in a browser. Initially, the dashboard may
   show `DISCONNECTED` until a serial port is selected. It must not claim the
   ESP32 is associated with a Wi-Fi access point.

4. If Vite cannot start because port `5173` is in use, stop the prior Vite
   process and rerun `npm run dev`; the configured frontend port is strict.

## Connect and verify live scans

1. Select and open the ESP32 port, replacing `COM8` with the detected port:

   ```powershell
   Invoke-RestMethod `
     -Method Put `
     -Uri "http://127.0.0.1:8000/api/serial/connection" `
     -ContentType "application/json" `
     -Body '{"port":"COM8"}'
   ```

2. Inspect the backend state:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8000/api/serial/state
   Invoke-RestMethod http://127.0.0.1:8000/api/live
   ```

   Expected: after accepted firmware messages, the serial state becomes
   `CONNECTED_IDLE` or `CONNECTED_SCANNING`; `/api/live` shows an increasing
   `scan_count` and the latest completed scan time. A successful empty scan is
   valid and has `networks: []`.

3. In the dashboard, verify all of the following:

   - The serial status shows the selected COM port and a connected state.
   - **Recording status** is independently shown as **Inactive**.
   - The nearby-networks table updates after completed scans.
   - Rows show SSID, BSSID, RSSI, channel, encryption, and last-observed time.
   - Empty SSIDs are shown as `Hidden network`; duplicate SSIDs remain distinct
     BSSID rows.
   - RSSI and SSID sorting both work.

4. In browser developer tools, inspect Network -> WebSocket. Confirm the
   connection to `/api/live` opens successfully and receives a `snapshot`, then
   `connection_state` and/or `scan_update` events. If the dashboard remains
   `Connecting`, restart `npm run dev` and confirm the Vite proxy is active.

## Verify error and connection-loss behavior

1. Disconnect the ESP32 USB cable or otherwise interrupt its serial connection.
2. Confirm the dashboard visibly reports either a serial-device error or a
   disconnected/reconnecting state; the browser must not report this as Wi-Fi
   access-point association loss.
3. Reconnect the ESP32, then explicitly retry the selected port if necessary:

   ```powershell
   Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/serial/reconnect
   ```

4. Confirm a connected serial state returns and the latest completed scan table
   resumes updating. The scan count and table are scoped to the current serial
   connection and may reset after reconnection.

## Verify live-only monitoring creates no scan data

1. Leave the dashboard connected long enough to observe multiple scans; the
   Phase 2 target is at least ten minutes for a full physical validation.
2. While recording remains **Inactive**, inspect the configured data directory.
   With default configuration, use:

   ```powershell
   Get-ChildItem -Force C:\Users\alyav\AirScan\data
   ```

   If `C:\Users\alyav\AirScan\data` does not exist, that is expected.
   If `AIRSCAN_DATA_DIR` is set, inspect that configured path instead.

3. Confirm no `master.jsonl`, session, recovery, or scan-observation files were
   created. Live scans are memory-only until a future recording feature exists.

## Automated regression checks

Run these before or after the physical check:

```powershell
cd C:\Users\alyav\AirScan\backend
.venv\Scripts\python.exe -m pytest

cd ..\frontend
npm test
npm run lint
npm run build
```

The backend suite includes a regression test proving that a successful live
scan can be returned by `/api/live` without creating the configured data
directory.