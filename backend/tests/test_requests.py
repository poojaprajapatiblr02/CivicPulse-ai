from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import requests
from app.api.requests import get_request_agent, get_request_store
from app.schemas.analysis import AnalyzeResponse
from app.schemas.requests import StoredRequest
from app.services.gemini_service import GeminiServiceError


@pytest.fixture
def setup(request_store, request_app):
    store = request_store
    agent = MagicMock()
    agent.analyze = AsyncMock(return_value=AnalyzeResponse(
        original_text="Demo Village 01 needs water", language="English", category="Water",
        sub_category="Water supply", problem="Water needed", location_name="Demo Village 01",
        urgency=0.6, confidence=0.9,
    ))
    app = request_app
    app.dependency_overrides[get_request_agent] = lambda: agent
    with TestClient(app) as client:
        yield client, store, agent


@pytest.mark.parametrize("path", ["/api/v1/requests", "/api/v1/requests/analyze"])
def test_create_and_resolve(setup, path: str) -> None:
    client, store, agent = setup
    store.client.query.return_value.result.return_value = [{
        "location_name": "Demo Village 01", "district": "Demo District 01", "latitude": 12.2, "longitude": 75.1,
    }]
    response = client.post(path, json={"text": agent.analyze.return_value.original_text})
    assert response.status_code == 201
    body = response.json()
    assert str(UUID(body["request_id"])) == response.headers["X-Request-ID"]
    assert body["district"] == "Demo District 01" and body["latitude"] == 12.2 and body["longitude"] == 75.1
    assert body["confidence"] == 0.9 and body["created_at"] == "2026-09-20T00:00:00Z"
    agent.analyze.assert_awaited_once_with(body["original_text"], request_id=body["request_id"])
    assert store.client.load_table_from_json.call_args.args[0][0]["request_id"] == body["request_id"]
    store.client.load_table_from_json.return_value.result.assert_called_once()


@pytest.mark.parametrize("operation", ["query", "load_table_from_json"])
def test_storage_failure_not_reported_as_success(setup, operation: str) -> None:
    client, store, agent = setup
    getattr(store.client, operation).side_effect = RuntimeError("private storage data")
    response = client.post("/api/v1/requests", json={"text": agent.analyze.return_value.original_text})
    assert response.status_code == 503
    assert "private" not in response.text


def test_agent_failure_never_writes(setup) -> None:
    client, store, agent = setup
    agent.analyze.side_effect = GeminiServiceError(502, "Invalid analysis")
    assert client.post("/api/v1/requests", json={"text": "hospital"}).status_code == 502
    store.client.load_table_from_json.assert_not_called()


@pytest.mark.parametrize("body", [{}, {"text": " "}, {"text": "hospital", "latitude": 12}, {"text": "hospital", "request_id": "caller"}])
def test_invalid_create_never_runs_agent_or_writes(setup, body: dict) -> None:
    client, store, agent = setup
    assert client.post("/api/v1/requests", json=body).status_code == 422
    agent.analyze.assert_not_called()
    store.client.load_table_from_json.assert_not_called()


def test_list_filters_without_gemini(setup) -> None:
    client, store, agent = setup
    response = client.get("/api/v1/requests", params={"category": "Water", "district": "Demo District 01", "language": "English"})
    assert response.status_code == 200 and response.json() == []
    agent.analyze.assert_not_called()
    parameters = {param.name: param.value for param in store.client.query.call_args.kwargs["job_config"].query_parameters}
    assert parameters == {"limit": 100, "category": "Water", "district": "Demo District 01", "language": "English"}


@pytest.mark.parametrize("params", [{"category": "Finance"}, {"language": "French"}, {"district": " "}, {"limit": 0}, {"limit": 1001}])
def test_invalid_filters(setup, params: dict) -> None:
    client, store, _ = setup
    assert client.get("/api/v1/requests", params=params).status_code == 422
    store.client.query.assert_not_called()


@pytest.mark.parametrize("confidence", [0.9, None])
def test_read_stored_and_legacy_records(setup, confidence: float | None) -> None:
    client, store, agent = setup
    row = {
        **agent.analyze.return_value.model_dump(), "request_id": "SYN-REQ-0001",
        "district": None, "latitude": None, "longitude": None, "confidence": confidence,
        "created_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
    }
    store.client.query.return_value.result.return_value = [row]
    response = client.get("/api/v1/requests")
    assert response.status_code == 200
    assert response.json() == [StoredRequest.model_validate(row).model_dump(mode="json")]
    assert "WHERE" not in store.client.query.call_args.args[0]
    agent.analyze.assert_not_called()


@pytest.mark.parametrize("invalid_data", [False, True])
def test_read_failure_is_redacted(setup, invalid_data: bool) -> None:
    client, store, _ = setup
    if invalid_data:
        store.client.query.return_value.result.return_value = [{"original_text": "private"}]
    else:
        store.client.query.side_effect = RuntimeError("private query data")
    response = client.get("/api/v1/requests")
    assert response.status_code == 503
    assert "private" not in response.text


@pytest.mark.parametrize("change", [{"latitude": 91.0}, {"district": " "}, {"longitude": None}])
def test_invalid_dataset_location_never_written(setup, change: dict) -> None:
    client, store, agent = setup
    store.client.query.return_value.result.return_value = [{
        "location_name": "Demo Village 01", "district": "Demo District 01", "latitude": 12.2, "longitude": 75.1, **change,
    }]
    assert client.post("/api/v1/requests", json={"text": agent.analyze.return_value.original_text}).status_code == 503
    store.client.load_table_from_json.assert_not_called()


def test_partial_stored_coordinates_rejected(setup) -> None:
    _, _, agent = setup
    with pytest.raises(ValidationError):
        StoredRequest(
            **agent.analyze.return_value.model_dump(), request_id="invalid", district=None,
            latitude=12.2, longitude=None, created_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
        )


def test_storage_configuration_is_safe(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(requests, "get_bigquery_settings", MagicMock(side_effect=ValueError("private config")))
    with pytest.raises(requests.HTTPException) as error:
        get_request_store()
    assert error.value.status_code == 503
    assert "private" not in error.value.detail + caplog.text


def test_storage_dependency_and_utc_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = MagicMock()
    factory = MagicMock()
    clock = MagicMock()
    monkeypatch.setattr(requests, "get_bigquery_settings", lambda: settings)
    monkeypatch.setattr(requests, "BigQueryService", factory)
    monkeypatch.setattr(requests, "datetime", clock)
    assert get_request_store() is factory.return_value
    factory.assert_called_once_with(settings)
    assert requests.get_created_at() is clock.now.return_value
    clock.now.assert_called_once_with(timezone.utc)