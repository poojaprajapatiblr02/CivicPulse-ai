from datetime import datetime, timedelta, timezone
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
import os
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import hotspots as hotspot_api
from app.core import config
from app.core.config import BigQuerySettings, HotspotSettings
from app.main import create_app
from app.schemas.bigquery import TABLE_SCHEMAS
from app.services.bigquery_service import BigQueryService, BigQueryServiceError
from app.services.hotspot_service import HotspotService, aggregate_hotspots
from app.services.priority_service import PriorityService


AS_OF = datetime(2026, 9, 20, tzinfo=timezone.utc)


def location(name: str = "Demo Village 01", district: str = "Demo District 01", population: int = 1200) -> dict:
    return {"location_name": name, "district": district, "population": population, "latitude": 12.5, "longitude": 77.5}


def request(index: int, days: int = 1, category: str = "Water", **changes) -> dict:
    return {
        "request_id": f"request-{index}", "location_name": "Demo Village 01",
        "district": "Demo District 01", "category": category, "urgency": 0.6,
        "created_at": AS_OF - timedelta(days=days), **changes,
    }


def test_known_aggregation_and_strict_threshold() -> None:
    rows = [request(index, days=1 if index < 14 else 31, urgency=0.8 if index < 14 else 0.2) for index in range(21)]
    result = aggregate_hotspots(rows, [location()], threshold=20, as_of=AS_OF)
    assert len(result) == 1
    hotspot = result[0]
    assert hotspot.request_count == 21
    assert hotspot.affected_population == 1200
    assert hotspot.average_urgency == pytest.approx(0.6)
    assert hotspot.demand_growth == pytest.approx(1.0)
    assert (hotspot.latitude, hotspot.longitude) == (12.5, 77.5)
    assert hotspot.created_at == AS_OF
    assert aggregate_hotspots(rows[:20], [location()], threshold=20, as_of=AS_OF) == []
    assert aggregate_hotspots(list(reversed(rows)), [location()], threshold=20, as_of=AS_OF)[0].hotspot_id == hotspot.hotspot_id


def test_distinct_groups_and_population_not_multiplied() -> None:
    rows = [request(index, category=category) for index, category in enumerate(["Water", "Water", "Roads", "Roads"])]
    rows += [request(4, district="Demo District 02"), request(5, district="Demo District 02")]
    rows += [request(6, location_name="Demo Village 02"), request(7, location_name="Demo Village 02")]
    locations = [location(), location(district="Demo District 02", population=500), location(name="Demo Village 02", population=600)]
    result = aggregate_hotspots(rows, locations, threshold=1, as_of=AS_OF)
    assert len(result) == 4
    assert sorted(item.affected_population for item in result) == [500, 600, 1200, 1200]
    assert len({item.hotspot_id for item in result}) == 4


def test_unresolved_ambiguous_and_future_requests_are_excluded() -> None:
    rows = [request(0, district=None), request(1, location_name="Unknown"), request(2, days=-1)]
    assert aggregate_hotspots(rows, [location()], threshold=0, as_of=AS_OF) == []
    assert aggregate_hotspots([request(0)], [location(), location(population=999)], threshold=0, as_of=AS_OF) == []


@pytest.mark.parametrize(("days", "expected"), [([1, 2], None), ([31, 32], -1.0), ([30, 60], 0.0), ([61, 62], 0.0)])
def test_growth_windows(days: list[int], expected: float | None) -> None:
    result = aggregate_hotspots([request(index, days=age) for index, age in enumerate(days)], [location()], threshold=0, as_of=AS_OF)
    assert result[0].demand_growth == expected


def test_duplicate_request_ids_and_identical_demographics_not_double_counted() -> None:
    result = aggregate_hotspots([request(0), request(0)], [location(), location()], threshold=0, as_of=AS_OF)
    assert result[0].request_count == 1
    assert result[0].affected_population == 1200


@pytest.fixture
def service() -> HotspotService:
    store = BigQueryService(BigQuerySettings(project_id="demo-project"), client=MagicMock())
    store.execute_query = MagicMock()
    return HotspotService(store, HotspotSettings(request_threshold=0))


@pytest.fixture
def hotspot():
    return aggregate_hotspots([request(0)], [location()], threshold=0, as_of=AS_OF)[0]


@pytest.fixture
def api(service, monkeypatch):
    monkeypatch.setattr(hotspot_api, "PriorityService", MagicMock())
    app = create_app(cors_origins=[])
    app.dependency_overrides[hotspot_api.get_hotspot_service] = lambda: service
    app.dependency_overrides[hotspot_api.get_detection_time] = lambda: AS_OF
    with TestClient(app) as client:
        yield client


def test_detect_persists_atomic_snapshot_before_return(api, service, hotspot) -> None:
    service.store.execute_query.side_effect = [[request(0)], [location()]]
    response = api.post("/api/v1/hotspots/detect")
    assert response.status_code == 200
    assert response.json() == [hotspot.model_dump(mode="json")]
    assert response.headers["X-Request-ID"]
    call = service.store.client.load_table_from_json.call_args
    assert call.args == ([hotspot.model_dump(mode="json")], "demo-project.civicpulse.hotspots")
    job_config = call.kwargs["job_config"]
    assert job_config.write_disposition == "WRITE_TRUNCATE"
    assert job_config.create_disposition == "CREATE_NEVER"
    assert job_config.schema == TABLE_SCHEMAS["hotspots"]
    service.store.client.load_table_from_json.return_value.result.assert_called_once_with(timeout=60)
    queries = service.store.execute_query.call_args_list
    assert "@as_of" in queries[0].args[0] and "LIMIT" not in queries[0].args[0]
    assert queries[0].args[1][1].value == AS_OF
    assert all("data_source = @source" in call.args[0] for call in queries)


def test_empty_detection_clears_stale_snapshot(api, service) -> None:
    service.store.execute_query.side_effect = [[], [location()], []]
    response = api.post("/api/v1/hotspots/detect")
    assert response.status_code == 200 and response.json() == []
    assert service.store.execute_query.call_args.args[0] == "DELETE FROM `demo-project.civicpulse.hotspots` WHERE TRUE"
    service.store.client.load_table_from_json.assert_not_called()


def test_get_map_rows_and_detail(api, service, hotspot) -> None:
    service.store.execute_query.return_value = [hotspot.model_dump()]
    response = api.get("/api/v1/hotspots?limit=25")
    assert response.status_code == 200
    assert response.json() == [hotspot.model_dump(mode="json")]
    query, parameters = service.store.execute_query.call_args.args
    assert "ORDER BY request_count DESC, hotspot_id LIMIT @limit" in query
    assert parameters[0].value == 25
    detail = api.get(f"/api/v1/hotspots/{hotspot.hotspot_id}")
    assert detail.status_code == 200 and detail.json() == response.json()[0]
    query, parameters = service.store.execute_query.call_args.args
    assert hotspot.hotspot_id not in query
    assert parameters[0].value == hotspot.hotspot_id
    service.store.execute_query.return_value = []
    assert api.get(f"/api/v1/hotspots/{hotspot.hotspot_id}").status_code == 404


@pytest.mark.parametrize("path", ["/api/v1/hotspots/not-a-uuid", "/api/v1/hotspots?limit=0", "/api/v1/hotspots?limit=1001"])
def test_invalid_api_input(api, service, path) -> None:
    assert api.get(path).status_code == 422
    service.store.execute_query.assert_not_called()


@pytest.mark.parametrize("path", ["/api/v1/hotspots", "/api/v1/hotspots/00000000-0000-0000-0000-000000000000", "/api/v1/hotspots/detect"])
def test_cloud_errors_are_safe(api, service, path, caplog) -> None:
    service.store.execute_query.side_effect = BigQueryServiceError("private source rows")
    response = api.post(path) if path.endswith("detect") else api.get(path)
    assert response.status_code == 503
    assert "private source rows" not in response.text + caplog.text


def test_write_failure_does_not_return_success(api, service, caplog) -> None:
    service.store.execute_query.side_effect = [[request(0)], [location()]]
    service.store.client.load_table_from_json.return_value.result.side_effect = RuntimeError("private load data")
    response = api.post("/api/v1/hotspots/detect")
    assert response.status_code == 503
    assert "private load data" not in response.text + caplog.text


def test_invalid_stored_hotspot_rejected(api, service) -> None:
    service.store.execute_query.return_value = [{"latitude": 999}]
    assert api.get("/api/v1/hotspots").status_code == 503


def test_invalid_source_does_not_replace_snapshot(api, service) -> None:
    service.store.execute_query.side_effect = [[request(0, urgency=2.0)], [location()]]
    assert api.post("/api/v1/hotspots/detect").status_code == 503
    service.store.client.load_table_from_json.assert_not_called()


def test_threshold_configuration(monkeypatch) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda *_: None)
    monkeypatch.delenv("HOTSPOT_REQUEST_THRESHOLD", raising=False)
    assert config.get_hotspot_settings().request_threshold == 20
    monkeypatch.setenv("HOTSPOT_REQUEST_THRESHOLD", "7")
    assert config.get_hotspot_settings().request_threshold == 7
    for value in ("-1", "invalid", "1.5"):
        monkeypatch.setenv("HOTSPOT_REQUEST_THRESHOLD", value)
        with pytest.raises(ValidationError):
            config.get_hotspot_settings()


def test_configuration_dependency(monkeypatch) -> None:
    monkeypatch.setattr(hotspot_api, "get_bigquery_settings", lambda: BigQuerySettings(project_id="demo-project"))
    monkeypatch.setattr(hotspot_api, "get_hotspot_settings", lambda: HotspotSettings())
    monkeypatch.setattr(hotspot_api, "BigQueryService", MagicMock())
    assert isinstance(hotspot_api.get_hotspot_service(), HotspotService)
    assert hotspot_api.get_detection_time().tzinfo is not None
    monkeypatch.setattr(hotspot_api, "get_hotspot_settings", MagicMock(side_effect=ValueError("private config")))
    with TestClient(create_app(cors_origins=[])) as client:
        response = client.get("/api/v1/hotspots")
    assert response.status_code == 503 and "private config" not in response.text


def test_invalid_limit_and_conflicting_ids(service) -> None:
    with pytest.raises(ValueError):
        service.list_hotspots(limit=0)
    with pytest.raises(ValueError, match="Conflicting"):
        aggregate_hotspots([request(0), request(0, urgency=0.9)], [location()], threshold=0, as_of=AS_OF)
    with pytest.raises(ValidationError):
        aggregate_hotspots([], [], threshold=0, as_of=AS_OF.replace(tzinfo=None))


@pytest.mark.hotspots_live
@pytest.mark.skipif(os.getenv("RUN_HOTSPOT_INTEGRATION") != "1", reason="Live hotspot snapshot writes are opt-in")
def test_live_hotspot_snapshot_and_map_reads() -> None:
    store = BigQueryService(config.get_bigquery_settings())
    counts_sql = f"SELECT COUNT(*) AS total FROM `{store.table_id('citizen_requests')}`"
    before = store.execute_query(counts_sql)[0]["total"]
    now = datetime.now(timezone.utc)
    source_rows = store.execute_query(
        f"SELECT district, location_name, category FROM `{store.table_id('citizen_requests')}` "
        "WHERE district IS NOT NULL AND location_name IS NOT NULL",
    )
    expected_counts = Counter((row["district"], row["location_name"], row["category"]) for row in source_rows)
    demo_service = HotspotService(store, HotspotSettings(request_threshold=0))
    app = create_app(cors_origins=[])
    app.dependency_overrides[hotspot_api.get_hotspot_service] = lambda: demo_service
    app.dependency_overrides[hotspot_api.get_detection_time] = lambda: now
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/hotspots/detect")
            assert response.status_code == 200, response.text
            detected = response.json()
            assert detected
            for hotspot in detected:
                assert hotspot["request_count"] == expected_counts[(hotspot["district"], hotspot["location_name"], hotspot["category"])]
                assert hotspot["latitude"] is not None and hotspot["longitude"] is not None
            listing = client.get("/api/v1/hotspots")
            assert listing.status_code == 200
            assert {row["hotspot_id"] for row in listing.json()} == {row["hotspot_id"] for row in detected}
            first = detected[0]
            detail = client.get(f"/api/v1/hotspots/{first['hotspot_id']}")
            assert detail.status_code == 200 and detail.json() == first
            gaps = client.get("/api/v1/gaps")
            priorities = client.get("/api/v1/priorities")
            assert gaps.status_code == priorities.status_code == 200
            ranked = priorities.json()
            assert len(ranked) == len(detected) == len(gaps.json())
            assert {row["hotspot_id"] for row in ranked} == {row["hotspot_id"] for row in detected}
            for row in ranked:
                assert row["scoring_status"] == "complete"
                expected = sum(Decimal(str(row[name])) * weight for name, weight in (
                    ("demand_score", Decimal("0.30")), ("infrastructure_gap_score", Decimal("0.20")),
                    ("population_impact_score", Decimal("0.15")), ("vulnerability_score", Decimal("0.15")),
                    ("urgency_score", Decimal("0.10")), ("investment_gap_score", Decimal("0.10")),
                )).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                assert Decimal(str(row["priority_score"])) == expected
            assert [row["priority_score"] for row in ranked] == sorted((row["priority_score"] for row in ranked), reverse=True)
    finally:
        restored = HotspotService(store, config.get_hotspot_settings()).detect(as_of=now)
        PriorityService(store).refresh(restored)
    assert store.execute_query(counts_sql)[0]["total"] == before