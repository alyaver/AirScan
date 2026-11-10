# AirScan

AirScan is an ESP32-based Wi-Fi scanner intended to detect nearby wireless networks and transmit signal data to a local PC application for analysis.

## Current status

The repository currently contains the initial ESP32 firmware project. The firmware scans nearby Wi-Fi networks and writes human-readable results to USB serial. 

For the confirmed firmware baseline, current serial-output limitations, and
planned development boundary, see
[docs/current-development-baseline.md](docs/current-development-baseline.md).

## Local backend

The initial FastAPI backend skeleton is located in
[`backend`](backend/README.md). It currently exposes only a local health
endpoint; serial communication, recording, storage, and the React dashboard
are planned for later tasks.
