import json
import logging
from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core import config
from app.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(cors_origins=["http://localhost:5173"])) as test_client:
        yield test_client


def test_health_returns_expected_response(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "civicpulse-backend",
    }


@pytest.mark.parametrize(
    ("origin", "expected_status", "allowed_origin"),
    [
        ("http://localhost:5173", 200, "http://localhost:5173"),
        ("https://untrusted.example", 400, None),
    ],
)
def test_cors_preflight(
    client: TestClient, origin: str, expected_status: int, allowed_origin: str | None
) -> None:
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == expected_status
    assert response.headers.get("access-control-allow-origin") == allowed_origin


def test_health_includes_cors_header(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health", headers={"Origin": "http://localhost:5173"}
    )

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unknown_route_returns_not_found(client: TestClient) -> None:
    assert client.get("/api/v1/missing").status_code == 404


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        (None, ["http://localhost:5173", "http://127.0.0.1:5173"]),
        (" http://localhost:5200, ,http://localhost:5300 ",
         ["http://localhost:5200", "http://localhost:5300"]),
        ("", []),
    ],
)
def test_cors_configuration(
    monkeypatch: pytest.MonkeyPatch, configured: str | None, expected: list[str]
) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda path: None)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    if configured is not None:
        monkeypatch.setenv("CORS_ORIGINS", configured)

    assert config.get_cors_origins() == expected


def test_request_logging(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        response = client.get("/api/v1/health?private=do-not-log")

    request_id = response.headers["X-Request-ID"]
    assert UUID(request_id).version == 4
    entry = json.loads(caplog.records[-1].message)
    assert entry["request_id"] == request_id
    assert entry["operation"] == "GET"
    assert entry["success"] is True
    assert entry["latency_ms"] >= 0
    assert "do-not-log" not in caplog.text


def test_unexpected_errors_are_safe(caplog: pytest.LogCaptureFixture) -> None:
    application = create_app(cors_origins=[])

    @application.get("/test-error")
    def failing_route() -> None:
        raise RuntimeError("private citizen information")

    with TestClient(application) as test_client:
        with caplog.at_level(logging.INFO, logger="uvicorn.error"):
            response = test_client.get("/test-error")

    assert response.status_code == 500
    assert response.text == "Internal server error"
    assert UUID(response.headers["X-Request-ID"]).version == 4
    assert json.loads(caplog.records[-1].message)["success"] is False
    assert "private citizen information" not in caplog.text