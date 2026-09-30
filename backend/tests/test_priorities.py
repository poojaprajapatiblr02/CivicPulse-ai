from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import priorities as priority_api
from app.api import hotspots as hotspot_api
from app.core.config import BigQuerySettings
from app.main import create_app
from app.schemas.bigquery import TABLE_SCHEMAS
from app.schemas.hotspots import Hotspot
from app.schemas.priorities import ScoreComponents
from app.services.gap_analysis_service import analyze_gaps
from app.services.priority_service import PriorityService, score_hotspots, weighted_priority
from app.services.bigquery_service import BigQueryService, BigQueryServiceError


def hotspot(identity="first", count=85, population=7800, urgency=0.82):
    return Hotspot(
        hotspot_id=identity, location_name=identity, district="Demo District", category="Water",
        request_count=count, affected_population=population, average_urgency=urgency,
        demand_growth=0.0, latitude=12.5, longitude=77.5,
        created_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
    )


def sources(identity="first", **overrides):
    key = {"location_name": identity, "district": "Demo District"}
    demographics = {**key, "vulnerability_index": 0.7}
    infrastructure = {**key, "category": "Water", "available_capacity": 9.0,
                      "required_capacity": 100.0, "capacity_unit": "households"}
    investments = {**key, "category": "Water", "investment_inr": Decimal("12"),
                   "estimated_need_inr": Decimal("100"), "financial_year": "2026-27", "currency": "INR"}
    infrastructure.update(overrides)
    return [demographics], [infrastructure], [investments]


def test_confirmed_additive_formula():
    scores = ScoreComponents(demand_score=85, infrastructure_gap_score=91,
        population_impact_score=78, vulnerability_score=70, urgency_score=82, investment_gap_score=88)
    assert weighted_priority(scores) == 82.9


@pytest.mark.parametrize("value", [0, 100])
def test_formula_endpoints(value):
    assert weighted_priority(ScoreComponents(**dict.fromkeys(ScoreComponents.model_fields, value))) == value


def test_known_sources_and_normalization_are_reproducible():
    first, largest = hotspot(), hotspot("largest", 100, 10000)
    evidence = analyze_gaps([first], *sources())
    results = score_hotspots([first, largest], evidence)
    record = next(row for row in results if row.hotspot_id == "first")
    assert record.demand_score == 85
    assert record.infrastructure_gap_score == 91
    assert record.population_impact_score == 78
    assert record.vulnerability_score == 70
    assert record.urgency_score == 82
    assert record.investment_gap_score == 88
    assert record.priority_score == 82.9
    assert record.capacity_gap == 91
    assert record.investment_gap_inr == Decimal("88")
    assert record.max_request_count == 100 and record.max_population == 10000
    assert record.scoring_status == "complete"
    assert results == score_hotspots([largest, first], evidence)


@pytest.mark.parametrize(("available", "required", "expected"), [(150, 100, 0), (0, 100, 100), (0, 0, 0)])
def test_capacity_bounds(available, required, expected):
    item = hotspot()
    evidence = analyze_gaps([item], *sources(available_capacity=available, required_capacity=required))
    assert score_hotspots([item], evidence)[0].infrastructure_gap_score == expected


def test_missing_inputs_not_fabricated():
    item = hotspot(population=0)
    results = score_hotspots([item], analyze_gaps([item], [], [], []))
    assert results[0].priority_score is None
    assert results[0].infrastructure_gap_score is None
    assert results[0].investment_gap_score is None
    assert results[0].vulnerability_score is None
    assert results[0].population_impact_score == 0
    assert results[0].scoring_status == "insufficient_data"
    assert score_hotspots([], {}) == []


def test_latest_investment_year_and_duplicate_sources():
    item = hotspot()
    demographics, infrastructure, investments = sources()
    investments.append({**investments[0], "financial_year": "2025-26", "investment_inr": Decimal("100")})
    result = score_hotspots([item], analyze_gaps([item], demographics * 2, infrastructure * 2, investments))[0]
    assert result.investment_gap_score == 88
    assert result.financial_year == "2026-27"
    infrastructure.append({**infrastructure[0], "capacity_unit": "litres"})
    result = score_hotspots([item], analyze_gaps([item], demographics, infrastructure, investments))[0]
    assert result.priority_score is None and "infrastructure" in result.data_issues


@pytest.fixture
def service():
    store = BigQueryService(BigQuerySettings(project_id="demo-project"), client=MagicMock())
    store.execute_query = MagicMock()
    return PriorityService(store)


@pytest.fixture
def api(service):
    app = create_app(cors_origins=[])
    app.dependency_overrides[priority_api.get_priority_service] = lambda: service
    with TestClient(app) as client:
        yield client


def test_refresh_persists_validated_evidence(service):
    item = hotspot()
    service.store.execute_query.side_effect = list(sources())
    results = service.refresh([item])
    assert results[0].priority_score is not None
    call = service.store.client.load_table_from_json.call_args
    assert call.args == ([results[0].model_dump(mode="json")], "demo-project.civicpulse.infrastructure_gaps")
    assert call.kwargs["job_config"].write_disposition == "WRITE_TRUNCATE"
    assert call.kwargs["job_config"].schema == TABLE_SCHEMAS["infrastructure_gaps"]
    service.store.client.load_table_from_json.return_value.result.assert_called_once()
    assert len(service.store.execute_query.call_args_list) == 3
    assert all("@source" in call.args[0] for call in service.store.execute_query.call_args_list)


def test_empty_refresh_removes_old_scores_without_source_reads(service):
    assert service.refresh([]) == []
    service.store.execute_query.assert_called_once_with("DELETE FROM `demo-project.civicpulse.infrastructure_gaps` WHERE TRUE")


@pytest.mark.parametrize(("path", "order"), [("gaps", "hotspot_id"), ("priorities", "priority_score DESC NULLS LAST")])
def test_read_scores_and_exclude_stale_snapshots(api, service, path, order):
    item = hotspot()
    result = score_hotspots([item], analyze_gaps([item], *sources()))[0]
    service.store.execute_query.return_value = [result.model_dump()]
    response = api.get(f"/api/v1/{path}?limit=20")
    assert response.status_code == 200
    assert response.json() == [result.model_dump(mode="json")]
    sql, parameters = service.store.execute_query.call_args.args
    assert "EXISTS" in sql and "hotspots" in sql
    assert " AS snapshot " in sql and " AS current " not in sql
    assert "hotspot_id = gaps.hotspot_id" in sql and "created_at = gaps.created_at" in sql
    assert order in sql and "LIMIT @limit" in sql
    assert parameters[0].value == 20


@pytest.mark.parametrize("path", ["gaps", "priorities"])
def test_api_errors_safe_and_bounds(api, service, path, caplog):
    assert api.get(f"/api/v1/{path}?limit=0").status_code == 422
    service.store.execute_query.assert_not_called()
    service.store.execute_query.side_effect = BigQueryServiceError("private source data")
    response = api.get(f"/api/v1/{path}")
    assert response.status_code == 503
    assert "private source data" not in response.text + caplog.text


def test_detect_refreshes_priorities(monkeypatch):
    item = hotspot()
    hotspot_service = MagicMock()
    hotspot_service.detect.return_value = [item]
    priority_service = MagicMock()
    factory = MagicMock(return_value=priority_service)
    monkeypatch.setattr(hotspot_api, "PriorityService", factory)
    app = create_app(cors_origins=[])
    app.dependency_overrides[hotspot_api.get_hotspot_service] = lambda: hotspot_service
    with TestClient(app) as client:
        response = client.post("/api/v1/hotspots/detect")
    assert response.status_code == 200
    factory.assert_called_once_with(hotspot_service.store)
    priority_service.refresh.assert_called_once_with([item])


def test_write_failure_is_redacted(service, caplog):
    service.store.execute_query.side_effect = list(sources())
    service.store.client.load_table_from_json.return_value.result.side_effect = RuntimeError("private load details")
    with pytest.raises(BigQueryServiceError):
        service.refresh([hotspot()])
    assert "private load details" not in caplog.text


@pytest.mark.parametrize(("component", "expected"), [
    ("demand_score", 30), ("infrastructure_gap_score", 20), ("population_impact_score", 15),
    ("vulnerability_score", 15), ("urgency_score", 10), ("investment_gap_score", 10),
])
def test_each_formula_weight(component, expected):
    values = dict.fromkeys(ScoreComponents.model_fields, 0)
    values[component] = 100
    assert weighted_priority(ScoreComponents(**values)) == expected


def test_rounding_is_half_up_and_reproducible():
    values = dict.fromkeys(ScoreComponents.model_fields, 0)
    values["urgency_score"] = 0.05
    assert weighted_priority(ScoreComponents(**values)) == 0.01
    item = hotspot(count=1, population=1)
    largest = hotspot("largest", count=3, population=3)
    result = score_hotspots([item, largest], analyze_gaps([item], *sources()))[0]
    assert result.demand_score == 33.33
    assert result.population_impact_score == 33.33


@pytest.mark.parametrize(("funded", "needed", "score"), [(150, 100, 0), (0, 100, 100), (0, 0, 0)])
def test_investment_gap_bounds(funded, needed, score):
    item = hotspot()
    demographics, infrastructure, investments = sources()
    investments[0].update(investment_inr=Decimal(funded), estimated_need_inr=Decimal(needed))
    result = score_hotspots([item], analyze_gaps([item], demographics, infrastructure, investments))[0]
    assert result.investment_gap_score == score
    assert result.investment_gap_inr == max(Decimal(0), Decimal(needed - funded))


def test_ambiguous_funding_and_demographics_are_unscored():
    item = hotspot()
    demographics, infrastructure, investments = sources()
    demographics.append({**demographics[0], "vulnerability_index": 0.9})
    investments.append({**investments[0], "investment_inr": Decimal("45")})
    result = score_hotspots([item], analyze_gaps([item], demographics, infrastructure, investments))[0]
    assert result.priority_score is None
    assert result.vulnerability_score is None and result.investment_gap_score is None


@pytest.mark.parametrize(("source_index", "field", "value"), [
    (0, "vulnerability_index", 1.1), (1, "available_capacity", -1),
    (1, "required_capacity", float("nan")), (2, "investment_inr", Decimal("-1")),
    (2, "financial_year", "2026-29"), (2, "currency", "USD"),
])
def test_invalid_source_values_rejected(source_index, field, value):
    records = sources()
    records[source_index][0][field] = value
    with pytest.raises(ValidationError):
        analyze_gaps([hotspot()], *records)


def test_protected_snapshots_and_limit(service):
    with pytest.raises(ValueError):
        service.store.replace_snapshot("citizen_requests", [])
    with pytest.raises(ValueError):
        service.list_results(limit=1001)
    service.store.execute_query.assert_not_called()


def test_invalid_stored_score_is_safe(api, service):
    service.store.execute_query.return_value = [{"priority_score": 200}]
    assert api.get("/api/v1/priorities").status_code == 503


def test_configuration_dependency(monkeypatch):
    monkeypatch.setattr(priority_api, "get_bigquery_settings", lambda: BigQuerySettings(project_id="demo-project"))
    monkeypatch.setattr(priority_api, "BigQueryService", MagicMock())
    assert isinstance(priority_api.get_priority_service(), PriorityService)
    monkeypatch.setattr(priority_api, "get_bigquery_settings", MagicMock(side_effect=ValueError("private config")))
    with TestClient(create_app(cors_origins=[])) as client:
        response = client.get("/api/v1/priorities")
    assert response.status_code == 503 and "private config" not in response.text


def test_scoring_failure_does_not_report_detection_success(monkeypatch):
    mock_hotspots = MagicMock()
    mock_hotspots.detect.return_value = [hotspot()]
    mock_priority = MagicMock()
    mock_priority.refresh.side_effect = BigQueryServiceError("private score failure")
    monkeypatch.setattr(hotspot_api, "PriorityService", MagicMock(return_value=mock_priority))
    app = create_app(cors_origins=[])
    app.dependency_overrides[hotspot_api.get_hotspot_service] = lambda: mock_hotspots
    with TestClient(app) as client:
        response = client.post("/api/v1/hotspots/detect")
    assert response.status_code == 503 and "private score failure" not in response.text