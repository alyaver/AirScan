# AirScan

AirScan is an ESP32-based Wi-Fi scanner intended to detect nearby wireless networks and transmit signal data to a local PC application for analysis.

## Current status

The repository currently contains the initial ESP32 firmware project. The firmware scans nearby Wi-Fi networks and writes human-readable results to USB serial. 

For the confirmed firmware baseline, current serial-output limitations, and
planned development boundary, see
[docs/current-development-baseline.md](docs/current-development-baseline.md).

## Local application

The repository includes a FastAPI backend with a local health endpoint and a
React dashboard that displays that endpoint's connection status through the
Vite development proxy. Serial communication, recording, storage, and live
Wi-Fi scan data are planned for later tasks.

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
