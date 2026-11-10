from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_endpoint_reports_available_backend() -> None:
    app = create_app(
        Settings(
            host="127.0.0.1",
            port=8000,
            serial_baud_rate=115200,
            data_dir=Path("data"),
        )
    )

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "airscan-backend",
        "host": "127.0.0.1",
        "port": 8000,
    }