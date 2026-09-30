from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.api.dashboard import get_bigquery_service
from app.main import create_app
from app.schemas.dashboard import DashboardSummary
from app.services.bigquery_service import BigQueryServiceError
from app.api import dashboard
from app.core import config
import pytest


def test_dashboard_summary() -> None:
    service = Mock()
    service.dashboard_summary.return_value = DashboardSummary(
        total_requests=500, requests_by_category={"Water": 500}, total_population=750000,
        infrastructure_records=250, total_investment="123456.78",
    )
    app = create_app(cors_origins=[])
    app.dependency_overrides[get_bigquery_service] = lambda: service
    with TestClient(app) as client:
        response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 200
    assert response.json() == {
        "total_requests": 500, "requests_by_category": {"Water": 500},
        "total_population": 750000, "infrastructure_records": 250,
        "total_investment": "123456.78", "currency": "INR", "data_source": "SYNTHETIC / DEMO DATA",
    }


def test_dashboard_redacts_service_errors() -> None:
    service = Mock()
    service.dashboard_summary.side_effect = BigQueryServiceError("private details")
    app = create_app(cors_origins=[])
    app.dependency_overrides[get_bigquery_service] = lambda: service
    with TestClient(app) as client:
        response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 503
    assert response.json() == {"detail": "Dashboard data is unavailable. Check BigQuery configuration and access."}
    assert "X-Request-ID" in response.headers


def test_missing_configuration_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda path: None)
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    get_bigquery_service.cache_clear()
    with TestClient(create_app(cors_origins=[])) as client:
        assert client.get("/api/v1/health").status_code == 200
        response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 503
    assert "project_id" not in response.text


def test_service_dependency_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_service = Mock()
    monkeypatch.setattr(dashboard, "get_bigquery_settings", lambda: "settings")
    factory = Mock(return_value=fake_service)
    monkeypatch.setattr(dashboard, "BigQueryService", factory)
    get_bigquery_service.cache_clear()
    try:
        assert get_bigquery_service() is fake_service
        assert get_bigquery_service() is fake_service
        factory.assert_called_once_with("settings")
    finally:
        get_bigquery_service.cache_clear()