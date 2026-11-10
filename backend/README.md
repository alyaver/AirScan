# AirScan Backend

This directory contains the local Python backend for AirScan. The current
milestone provides only a FastAPI application skeleton and a health endpoint.
Serial communication, recording, storage, and frontend integration are not
implemented yet.

## Requirements

- Python 3.10 or newer.

## Windows setup

From `C:\Users\alyav\AirScan\backend` in PowerShell:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

If PowerShell blocks activation, use a Command Prompt instead:

```bat
.venv\Scripts\activate.bat
```

## Run locally

With the virtual environment activated, run:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The health endpoint is available at:

```text
http://127.0.0.1:8000/api/health
```

## Configuration

The application uses local-safe defaults and can be configured with environment
variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `AIRSCAN_HOST` | `127.0.0.1` | Host used by documented local startup commands. |
| `AIRSCAN_PORT` | `8000` | Backend HTTP port. |
| `AIRSCAN_SERIAL_BAUD_RATE` | `115200` | Reserved serial baud rate for the ESP32 integration task. |
| `AIRSCAN_DATA_DIR` | `<repository>\data` | Reserved local data directory for the storage task. |

`AIRSCAN_HOST` and `AIRSCAN_PORT` configure application metadata. The explicit
Uvicorn command remains responsible for the actual network binding.

## Tests

Run from this directory with the virtual environment activated:

```powershell
python -m pytest
```