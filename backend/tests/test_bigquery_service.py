from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from google.cloud import bigquery
from pydantic import ValidationError

from app.core.config import BigQuerySettings
from app.core import config
from app.schemas.bigquery import TABLE_SCHEMAS
from app.schemas.analysis import AnalyzeResponse
from app.services.bigquery_service import BigQueryService, BigQueryServiceError


@pytest.fixture
def service() -> BigQueryService:
    return BigQueryService(
        BigQuerySettings(project_id="demo-project", dataset="civicpulse", location="asia-south1"),
        client=MagicMock(),
    )


@pytest.mark.parametrize("project", ["", "demo`project", "demo.project", "demo; DROP TABLE"])
def test_rejects_unsafe_project_identifiers(project: str) -> None:
    with pytest.raises(ValidationError):
        BigQuerySettings(project_id=project)


def test_parameterized_query_and_billing_cap(service: BigQueryService) -> None:
    service.client.query.return_value.result.return_value = [{"category": "Water"}]
    parameter = bigquery.ScalarQueryParameter("category", "STRING", "Water' OR 1=1")
    assert service.execute_query("SELECT @category AS category", [parameter]) == [{"category": "Water"}]
    call = service.client.query.call_args
    assert call.args[0] == "SELECT @category AS category"
    assert call.kwargs["job_config"].query_parameters == [parameter]
    assert call.kwargs["job_config"].maximum_bytes_billed == 100_000_000
    assert call.kwargs["location"] == "asia-south1"


def test_staged_table_prefix_keeps_logical_table_allowlist():
    store = BigQueryService(BigQuerySettings(project_id='demo-project', table_prefix='statewide_'), client=MagicMock())
    assert store.table_id('demographics') == 'demo-project.civicpulse.statewide_demographics'
    with pytest.raises(ValueError):
        store.table_id('statewide_demographics')


@pytest.mark.parametrize('prefix', ['bad.name', 'bad`name', 'bad-name', '1bad'])
def test_unsafe_table_prefix_is_rejected(prefix):
    with pytest.raises(ValidationError):
        BigQuerySettings(project_id='demo-project', table_prefix=prefix)


def test_table_prefix_comes_from_environment(monkeypatch):
    monkeypatch.setattr(config, 'load_dotenv', lambda *args: None)
    monkeypatch.setenv('GCP_PROJECT_ID', 'demo-project')
    monkeypatch.setenv('BIGQUERY_TABLE_PREFIX', 'statewide_')
    assert config.get_bigquery_settings().table_prefix == 'statewide_'


def test_query_records_parameters(service: BigQueryService) -> None:
    service.client.query.return_value.result.return_value = []
    service.query_records("citizen_requests", category="Water", limit=20)
    call = service.client.query.call_args
    assert "`demo-project.civicpulse.citizen_requests`" in call.args[0]
    assert "category = @category" in call.args[0]
    assert "LIMIT @limit" in call.args[0]
    assert [parameter.value for parameter in call.kwargs["job_config"].query_parameters] == [20, "Water"]


@pytest.mark.parametrize("table", ["unknown", "citizen_requests`; DROP TABLE demo", ""])
def test_unknown_table_rejected(service: BigQueryService, table: str) -> None:
    with pytest.raises(ValueError):
        service.query_records(table)
    service.client.query.assert_not_called()


@pytest.mark.parametrize("limit", [0, 1001, -1])
def test_invalid_limit_rejected(service: BigQueryService, limit: int) -> None:
    with pytest.raises(ValueError):
        service.query_records("citizen_requests", limit=limit)


def test_demographic_category_filter_rejected(service: BigQueryService) -> None:
    with pytest.raises(ValueError):
        service.query_records("demographics", category="Water")


def test_insert_uses_explicit_schema_and_waits(service: BigQueryService) -> None:
    records = [{"request_id": "SYN-REQ-0001"}]
    assert service.insert_records("citizen_requests", records) == 1
    call = service.client.load_table_from_json.call_args
    assert call.args == (records, "demo-project.civicpulse.citizen_requests")
    assert call.kwargs["job_config"].write_disposition == "WRITE_APPEND"
    assert call.kwargs["job_config"].schema == TABLE_SCHEMAS["citizen_requests"]
    service.client.load_table_from_json.return_value.result.assert_called_once()


def test_empty_insert_is_noop(service: BigQueryService) -> None:
    assert service.insert_records("citizen_requests", []) == 0
    service.client.load_table_from_json.assert_not_called()


@pytest.mark.parametrize("operation", ["query", "load_table_from_json"])
def test_cloud_errors_are_redacted(service: BigQueryService, operation: str) -> None:
    getattr(service.client, operation).side_effect = RuntimeError("private details")
    with pytest.raises(BigQueryServiceError, match="BigQuery operation failed") as error:
        if operation == "query":
            service.execute_query("SELECT 1")
        else:
            service.insert_records("citizen_requests", [{"request_id": "example"}])
    assert "private" not in str(error.value)


def test_summary_avoids_join_multiplication(service: BigQueryService) -> None:
    service.client.query.return_value.result.return_value = [{
        "total_requests": 500, "requests_by_category": [{"category": "Water", "request_count": 500}],
        "total_population": 750000, "infrastructure_records": 250,
        "total_investment": Decimal("123456.78"),
    }]
    summary = service.dashboard_summary()
    assert summary.total_requests == 500
    assert summary.requests_by_category["Water"] == 500
    assert summary.requests_by_category["Healthcare"] == 0
    assert summary.total_investment == Decimal("123456.78")
    assert summary.currency == "INR"
    assert summary.data_source == "SYNTHETIC / DEMO DATA"
    query = service.client.query.call_args.args[0]
    assert "JOIN" not in query.upper()
    assert "COALESCE(SUM(investment_inr), 0)" in query


def test_empty_summary(service: BigQueryService) -> None:
    service.client.query.return_value.result.return_value = [{
        "total_requests": 0, "requests_by_category": [], "total_population": 0,
        "infrastructure_records": 0, "total_investment": Decimal("0"),
    }]
    summary = service.dashboard_summary()
    assert summary.total_requests == 0
    assert summary.total_population == 0
    assert all(count == 0 for count in summary.requests_by_category.values())


def test_default_client_uses_adc(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = MagicMock()
    monkeypatch.setattr(bigquery, "Client", factory)
    BigQueryService(BigQuerySettings(project_id="demo-project"))
    factory.assert_called_once_with(project="demo-project", location="asia-south1")


def test_query_without_filter(service: BigQueryService) -> None:
    service.client.query.return_value.result.return_value = []
    service.query_records("demographics")
    assert "WHERE" not in service.client.query.call_args.args[0]


@pytest.mark.parametrize("dataset", ["bad.dataset", "name`; DELETE", ""])
def test_invalid_dataset(dataset: str) -> None:
    with pytest.raises(ValidationError):
        BigQuerySettings(project_id="demo-project", dataset=dataset)


def test_environment_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda path: None)
    for key, value in {
        "GCP_PROJECT_ID": "demo-project", "BIGQUERY_DATASET": "demo_data",
        "BIGQUERY_LOCATION": "US", "BIGQUERY_MAX_BYTES_BILLED": "20000000",
    }.items():
        monkeypatch.setenv(key, value)
    settings = config.get_bigquery_settings()
    assert settings.project_id == "demo-project"
    assert settings.dataset == "demo_data"
    assert settings.location == "US"
    assert settings.maximum_bytes_billed == 20_000_000


@pytest.mark.parametrize("matches", [[], [
    {"location_name": "Demo Village 01", "district": "Demo District 01", "latitude": 12.2, "longitude": 75.1},
    {"location_name": "Demo Village 01", "district": "Demo District 02", "latitude": 13.2, "longitude": 76.1},
]])
def test_unresolved_or_ambiguous_location(service: BigQueryService, matches: list) -> None:
    service.client.query.return_value.result.return_value = matches
    assert service.resolve_location("Demo Village 01") is None


def test_location_uses_synthetic_parameterized_lookup(service: BigQueryService) -> None:
    location = {"location_name": "Demo Village 01", "district": "Demo District 01", "latitude": 12.2, "longitude": 75.1}
    service.client.query.return_value.result.return_value = [location]
    assert service.resolve_location("Demo Village 01").model_dump() == location
    call = service.client.query.call_args
    assert "demographics" in call.args[0]
    assert "@location_name" in call.args[0] and "@data_source" in call.args[0]
    assert "Demo Village 01" not in call.args[0]
    assert {parameter.name: parameter.value for parameter in call.kwargs["job_config"].query_parameters} == {
        "location_name": "Demo Village 01", "data_source": "SYNTHETIC / DEMO DATA",
    }


@pytest.mark.parametrize("location_name", [None, "Unknown Place", "Demo Village 01"])
def test_store_request_confirms_write(service: BigQueryService, location_name: str | None) -> None:
    location = {"location_name": "Demo Village 01", "district": "Demo District 01", "latitude": 12.2, "longitude": 75.1}
    service.client.query.return_value.result.return_value = [location] if location_name == "Demo Village 01" else []
    analysis = AnalyzeResponse(
        original_text="Need a hospital", language="English", category="Healthcare",
        sub_category="Hospital", problem="Need a hospital", location_name=location_name,
        urgency=0.7, confidence=0.9,
    )
    created = datetime(2026, 9, 20, tzinfo=timezone.utc)
    stored = service.store_request(analysis, request_id="test-request", created_at=created)
    assert stored.request_id == "test-request"
    assert stored.created_at == created
    assert stored.confidence == 0.9
    assert stored.latitude == (12.2 if location_name == "Demo Village 01" else None)
    assert stored.district == ("Demo District 01" if location_name == "Demo Village 01" else None)
    records = service.client.load_table_from_json.call_args.args[0]
    assert records == [{**stored.model_dump(mode="json"), "data_source": "SYNTHETIC / DEMO DATA"}]
    service.client.load_table_from_json.return_value.result.assert_called_once()
    if location_name is None:
        service.client.query.assert_not_called()


def test_request_filters_are_bound(service: BigQueryService) -> None:
    service.client.query.return_value.result.return_value = []
    assert service.list_requests(category="Other", district="town' OR 1=1 --", language="Hindi", limit=15) == []
    call = service.client.query.call_args
    sql = call.args[0]
    assert "category = @category" in sql and "district = @district" in sql and "language = @language" in sql
    assert "ORDER BY created_at DESC, request_id" in sql
    assert "town'" not in sql
    assert {parameter.name: parameter.value for parameter in call.kwargs["job_config"].query_parameters} == {
        "category": "Other", "district": "town' OR 1=1 --", "language": "Hindi", "limit": 15,
    }