import asyncio
import json
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from langsmith import tracing_context
from langsmith.run_helpers import get_tracing_context
from pydantic import ValidationError

from app.api import recommendations as recommendation_api
from app.core.config import BigQuerySettings, GeminiSettings, HotspotSettings
from app.core import config
from app.main import create_app
from app.agents.recommendation_agent import RecommendationAgent, validate_recommendation
from app.schemas.recommendations import EvidenceSnapshot, RecommendationDraft, RecommendationState, StoredRecommendation
from app.schemas.priorities import PriorityRecord
from app.services.bigquery_service import BigQueryService, BigQueryServiceError
from app.services.recommendation_service import RecommendationService, RecommendationEvidenceError, build_evidence
from app.services.gemini_service import GeminiService, GeminiServiceError
from app.services.hotspot_service import HotspotService
from app.services.priority_service import PriorityService


HOTSPOT_ID = "b6af59a5-92ef-47dd-a364-e810f829d046"
NOW = datetime(2026, 9, 20, tzinfo=timezone.utc)


@pytest.fixture
def evidence():
    return EvidenceSnapshot(
        hotspot_id=HOTSPOT_ID, hotspot_created_at=NOW, category="Healthcare",
        location_name="Demo Village 01", district="Demo District 01",
        facts={
            "request_count": "Citizen request count: 1240 requests",
            "population": "Locality population proxy: 85000 people",
            "infrastructure_gap_score": "Infrastructure gap score: 91 out of 100",
            "priority_score": "Development priority score: 86 out of 100",
            "investment_inr": "Recorded government investment: 1200000 INR",
            "asset_count": "Recorded infrastructure asset count: 1 Hospital",
            "average_distance_km": "Recorded average service distance: 18 km",
        },
        limitations=["Synthetic demonstration data; not verified government statistics."],
    )


@pytest.fixture
def draft():
    return RecommendationDraft(
        recommended_intervention="Assess additional primary healthcare facilities",
        reasoning=["{{request_count}}. {{infrastructure_gap_score}}. These support reviewing service availability."],
        evidence_keys=["request_count", "infrastructure_gap_score", "priority_score"],
        expected_impact="May improve access to primary care, subject to local feasibility review.",
        confidence=0.91,
        limitations=["Site suitability and operating costs require assessment."],
    )


def test_backend_renders_only_cited_numeric_evidence(evidence, draft):
    result = validate_recommendation(draft, evidence)
    assert result.evidence == [evidence.facts[key] for key in draft.evidence_keys]
    assert "1240" in result.reasoning[0] and "91 out of 100" in result.reasoning[0]
    assert "{{" not in result.reasoning[0]
    assert result.confidence == 0.91
    assert evidence.limitations[0] in result.limitations


@pytest.mark.parametrize("claim", [
    "Build 3 hospitals", "Build three hospitals", "Reduce travel by 50%",
    "Serve ninety thousand people", "Double capacity", "Cut travel in half",
    "Spend 1e6 INR", "Serve \u0661\u0662\u0663 residents", "Build a dozen clinics",
])
def test_model_cannot_introduce_numeric_claims(evidence, draft, claim):
    invalid = draft.model_copy(update={"expected_impact": claim})
    with pytest.raises(GeminiServiceError) as error:
        validate_recommendation(invalid, evidence)
    assert error.value.status_code == 502


@pytest.mark.parametrize("text", ["{{invented_budget}}", "{{asset_count}}", "{{request_count", "86 is the priority"])
def test_unknown_uncited_and_malformed_references_rejected(evidence, draft, text):
    with pytest.raises(GeminiServiceError):
        validate_recommendation(draft.model_copy(update={"reasoning": [text]}), evidence)


def test_agent_uses_langgraph_and_backend_snapshot(evidence, draft, caplog):
    service = MagicMock()
    service.settings.timeout_seconds = 30
    service.generate_structured = AsyncMock(return_value=draft)
    with caplog.at_level("INFO", logger="uvicorn.error"):
        result = asyncio.run(RecommendationAgent(service).generate(evidence, request_id="test-request"))
    assert result == validate_recommendation(draft, evidence)
    call = service.generate_structured.call_args.kwargs
    assert call["response_model"] is RecommendationDraft
    assert "85000" in call["text"] and "18 km" in call["text"]
    assert "1240" not in caplog.text and "Demo Village" not in caplog.text
    assert "recommendation_generation" in caplog.text and "recommendation_validation" in caplog.text


@pytest.fixture
def priority():
    return PriorityRecord(
        hotspot_id=HOTSPOT_ID, location_name="Demo Village 01", district="Demo District 01", category="Healthcare",
        request_count=1240, affected_population=85000, average_urgency=0.82,
        demand_growth=None, latitude=12.5, longitude=77.5, created_at=NOW,
        demand_score=85, infrastructure_gap_score=91, population_impact_score=78,
        vulnerability_score=70, urgency_score=82, investment_gap_score=88, priority_score=82.9,
        available_capacity=9, required_capacity=100, capacity_gap=91, capacity_unit="patients",
        vulnerability_index=0.7, investment_inr=Decimal("12"), estimated_need_inr=Decimal("100"),
        investment_gap_inr=Decimal("88"), financial_year="2026-27", max_request_count=1460,
        max_population=109000, scoring_status="complete",
    )


@pytest.fixture
def infrastructure(priority):
    return {
        "location_name": priority.location_name, "district": priority.district, "category": priority.category,
        "available_capacity": priority.available_capacity, "required_capacity": priority.required_capacity,
        "capacity_unit": priority.capacity_unit, "asset_type": "Hospital", "asset_count": 1,
        "average_distance_km": 18.0,
    }


@pytest.fixture
def storage():
    store = BigQueryService(BigQuerySettings(project_id="demo-project"), client=MagicMock())
    store.execute_query = MagicMock()
    return RecommendationService(store)


@pytest.fixture
def api(storage, draft):
    app = create_app(cors_origins=[])
    gemini = MagicMock()
    gemini.settings.timeout_seconds = 30
    gemini.generate_structured = AsyncMock(return_value=draft)
    app.dependency_overrides[recommendation_api.get_recommendation_service] = lambda: storage
    app.dependency_overrides[recommendation_api.get_recommendation_agent] = lambda: RecommendationAgent(gemini)
    app.dependency_overrides[recommendation_api.get_created_at] = lambda: NOW
    with TestClient(app) as client:
        yield client, gemini


def test_backend_evidence_contains_exact_sources(priority, infrastructure):
    snapshot = build_evidence(priority, [infrastructure])
    assert "1240" in snapshot.facts["request_count"]
    assert "85000" in snapshot.facts["population"]
    assert "82.9" in snapshot.facts["priority_score"]
    assert "18" in snapshot.facts["average_distance_km"]
    assert "12 INR" in snapshot.facts["investment_inr"]


def test_generate_and_store_only_after_validating(api, storage, priority, infrastructure):
    client, gemini = api
    storage.store.execute_query.side_effect = [[priority.model_dump()], [infrastructure], [{"hotspot_id": HOTSPOT_ID}]]
    response = client.post("/api/v1/recommendations/generate", json={"hotspot_id": HOTSPOT_ID})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["recommendation_id"] == response.headers["X-Request-ID"]
    assert body["hotspot_id"] == HOTSPOT_ID and body["created_at"] == "2026-09-20T00:00:00Z"
    assert body["evidence_snapshot"]["facts"]["priority_score"].endswith("82.9 out of 100")
    call = storage.store.client.load_table_from_json.call_args
    assert call.args[1] == "demo-project.civicpulse.recommendations"
    assert call.kwargs["job_config"].write_disposition == "WRITE_APPEND"
    assert isinstance(call.args[0][0]["evidence_snapshot"], str)
    storage.store.client.load_table_from_json.return_value.result.assert_called_once()
    gemini.generate_structured.assert_awaited_once()


def test_invalid_model_does_not_write(api, storage, priority, infrastructure):
    client, gemini = api
    gemini.generate_structured.return_value = RecommendationDraft(
        recommended_intervention="Build 3 hospitals", reasoning=["{{request_count}}"],
        evidence_keys=["request_count", "infrastructure_gap_score", "priority_score"],
        expected_impact="Access may improve.", confidence=0.9, limitations=["Needs review."],
    )
    storage.store.execute_query.side_effect = [[priority.model_dump()], [infrastructure]]
    assert client.post("/api/v1/recommendations/generate", json={"hotspot_id": HOTSPOT_ID}).status_code == 502
    storage.store.client.load_table_from_json.assert_not_called()


@pytest.mark.parametrize("payload", [{}, {"hotspot_id": "invalid"}, {"hotspot_id": HOTSPOT_ID, "population": 999}])
def test_caller_cannot_supply_evidence(api, storage, payload):
    client, gemini = api
    assert client.post("/api/v1/recommendations/generate", json=payload).status_code == 422
    storage.store.execute_query.assert_not_called()
    gemini.generate_structured.assert_not_called()


@pytest.mark.parametrize("text", ["Build {{request_count}} hospitals", "{{priority_score}} percent improvement", "{{request_count}} plus {{population}}"])
def test_cannot_relabel_or_repurpose_referenced_values(evidence, draft, text):
    with pytest.raises(GeminiServiceError):
        validate_recommendation(draft.model_copy(update={"reasoning": [text]}), evidence)


@pytest.mark.parametrize("keys", [
    ["request_count", "request_count", "priority_score"],
    ["request_count", "population", "priority_score"],
    ["request_count", "infrastructure_gap_score", "priority_score", "required_capacity"],
])
def test_bad_citations_rejected(evidence, draft, keys):
    with pytest.raises(GeminiServiceError):
        validate_recommendation(draft.model_copy(update={"evidence_keys": keys}), evidence)


@pytest.mark.parametrize(("change", "status"), [(None, 404), ("stale", 409), ("incomplete", 409)])
def test_missing_scored_hotspot_never_calls_gemini(api, storage, priority, change, status):
    client, gemini = api
    if change == "incomplete":
        storage.store.execute_query.side_effect = [[{**priority.model_dump(), "scoring_status": "insufficient_data"}], []]
    else:
        storage.store.execute_query.side_effect = [[], [] if change is None else [{"hotspot_id": HOTSPOT_ID}]]
    assert client.post("/api/v1/recommendations/generate", json={"hotspot_id": HOTSPOT_ID}).status_code == status
    gemini.generate_structured.assert_not_called()
    storage.store.client.load_table_from_json.assert_not_called()


@pytest.mark.parametrize("kind", ["missing", "ambiguous", "changed"])
def test_infrastructure_must_match_scored_evidence(priority, infrastructure, kind):
    rows = [] if kind == "missing" else [infrastructure, {**infrastructure, "asset_count": 2}] if kind == "ambiguous" else [{**infrastructure, "available_capacity": 99}]
    with pytest.raises(RecommendationEvidenceError) as error:
        build_evidence(priority, rows)
    assert error.value.status_code == 409


def test_missing_distance_is_not_invented(priority, infrastructure):
    snapshot = build_evidence(priority, [{**infrastructure, "average_distance_km": None}])
    assert "average_distance_km" not in snapshot.facts
    assert any("distance is unavailable" in text for text in snapshot.limitations)


def test_snapshot_change_during_generation_prevents_write(api, storage, priority, infrastructure):
    client, _ = api
    storage.store.execute_query.side_effect = [[priority.model_dump()], [infrastructure], []]
    assert client.post("/api/v1/recommendations/generate", json={"hotspot_id": HOTSPOT_ID}).status_code == 409
    storage.store.client.load_table_from_json.assert_not_called()


def test_list_and_detail_preserve_evidence_snapshot(api, storage, evidence, draft):
    client, _ = api
    stored = StoredRecommendation(
        **validate_recommendation(draft, evidence).model_dump(), recommendation_id=HOTSPOT_ID,
        hotspot_id=HOTSPOT_ID, created_at=NOW, evidence_snapshot=evidence,
    )
    row = {**stored.model_dump(), "evidence_snapshot": evidence.model_dump_json()}
    storage.store.execute_query.return_value = [row]
    listing = client.get("/api/v1/recommendations?limit=12")
    assert listing.status_code == 200 and listing.json() == [stored.model_dump(mode="json")]
    sql, parameters = storage.store.execute_query.call_args.args
    assert "ORDER BY created_at DESC" in sql and parameters[0].value == 12
    response = client.get(f"/api/v1/recommendations/{HOTSPOT_ID}")
    assert response.status_code == 200 and response.json() == listing.json()[0]
    sql, parameters = storage.store.execute_query.call_args.args
    assert HOTSPOT_ID not in sql and parameters[0].value == HOTSPOT_ID
    storage.store.execute_query.return_value = []
    assert client.get(f"/api/v1/recommendations/{HOTSPOT_ID}").status_code == 404


@pytest.mark.parametrize("path", ["/api/v1/recommendations?limit=0", "/api/v1/recommendations?limit=1001", "/api/v1/recommendations/invalid"])
def test_invalid_read_input(api, storage, path):
    client, _ = api
    assert client.get(path).status_code == 422
    storage.store.execute_query.assert_not_called()


@pytest.mark.parametrize("path", ["/api/v1/recommendations", f"/api/v1/recommendations/{HOTSPOT_ID}"])
def test_read_errors_are_safe(api, storage, path, caplog):
    client, _ = api
    storage.store.execute_query.side_effect = BigQueryServiceError("private raw source")
    response = client.get(path)
    assert response.status_code == 503 and "private raw source" not in response.text + caplog.text


def test_write_errors_are_safe(api, storage, priority, infrastructure, caplog):
    client, _ = api
    storage.store.execute_query.side_effect = [[priority.model_dump()], [infrastructure], [{"hotspot_id": HOTSPOT_ID}]]
    storage.store.client.load_table_from_json.return_value.result.side_effect = RuntimeError("private source")
    response = client.post("/api/v1/recommendations/generate", json={"hotspot_id": HOTSPOT_ID})
    assert response.status_code == 503 and "private source" not in response.text + caplog.text


def test_malformed_stored_snapshot_is_safe(api, storage):
    client, _ = api
    storage.store.execute_query.return_value = [{"evidence_snapshot": "not json"}]
    assert client.get("/api/v1/recommendations").status_code == 503
    with pytest.raises(ValueError):
        storage.list_recommendations(limit=0)


@pytest.mark.parametrize(("failure", "status"), [
    (GeminiServiceError(503, "Gemini unavailable"), 503),
    (TimeoutError(), 504), (RuntimeError("private error"), 503),
    ({"confidence": 2}, 502),
])
def test_agent_errors(evidence, failure, status):
    service = MagicMock()
    service.settings.timeout_seconds = 30
    service.generate_structured = AsyncMock(side_effect=[failure])
    with pytest.raises(GeminiServiceError) as error:
        asyncio.run(RecommendationAgent(service).generate(evidence, request_id="failure"))
    assert error.value.status_code == status


def test_tracing_disabled_and_context_restored(evidence, draft):
    service = MagicMock()
    service.settings.timeout_seconds = 30

    async def generate(**kwargs):
        assert get_tracing_context()["enabled"] is False
        return draft

    service.generate_structured = AsyncMock(side_effect=generate)
    trace_client = MagicMock()
    with tracing_context(enabled=True, client=trace_client):
        asyncio.run(RecommendationAgent(service).generate(evidence, request_id="privacy"))
        assert get_tracing_context()["enabled"] is True
    trace_client.create_run.assert_not_called()


def test_incomplete_graph_results_rejected(evidence):
    service = MagicMock()
    service.settings.timeout_seconds = 30
    agent = RecommendationAgent(service)
    state = RecommendationState(request_id="incomplete", evidence_snapshot=evidence)
    with pytest.raises(GeminiServiceError):
        asyncio.run(agent._validate(state))
    agent.graph = MagicMock()
    agent.graph.ainvoke = AsyncMock(return_value=state.model_dump())
    with pytest.raises(GeminiServiceError):
        asyncio.run(agent.generate(evidence, request_id="incomplete"))


@pytest.mark.parametrize("invalid", ["", "   ", "x" * 2001])
def test_blank_and_oversized_text_rejected(draft, invalid):
    with pytest.raises(ValidationError):
        RecommendationDraft.model_validate({**draft.model_dump(), "reasoning": [invalid]})


def test_dependency_configuration(monkeypatch):
    monkeypatch.setattr(recommendation_api, "get_bigquery_settings", lambda: BigQuerySettings(project_id="demo-project"))
    monkeypatch.setattr(recommendation_api, "BigQueryService", MagicMock())
    assert isinstance(recommendation_api.get_recommendation_service(), RecommendationService)
    assert isinstance(recommendation_api.get_recommendation_agent(MagicMock()), RecommendationAgent)
    monkeypatch.setattr(recommendation_api, "get_bigquery_settings", MagicMock(side_effect=ValueError("private config")))
    with TestClient(create_app(cors_origins=[])) as client:
        response = client.get("/api/v1/recommendations")
    assert response.status_code == 503 and "private config" not in response.text


@pytest.mark.parametrize("malformed", [False, True])
def test_real_gemini_service_with_mocked_model_transport(evidence, draft, malformed):
    client = MagicMock()
    client.__enter__.return_value = client
    client.aio.__aenter__ = AsyncMock(return_value=client.aio)
    client.aio.__aexit__ = AsyncMock(return_value=False)
    client.aio.models.generate_content = AsyncMock(return_value=MagicMock(text="not json" if malformed else draft.model_dump_json()))
    service = GeminiService(GeminiSettings(project_id="demo-project", region="global", model="gemini-3.1-flash-lite"), client_factory=lambda: client)
    if malformed:
        with pytest.raises(GeminiServiceError) as error:
            asyncio.run(RecommendationAgent(service).generate(evidence, request_id="sdk"))
        assert error.value.status_code == 502
    else:
        result = asyncio.run(RecommendationAgent(service).generate(evidence, request_id="sdk"))
        assert result.evidence[0] == evidence.facts["request_count"]
        call = client.aio.models.generate_content.call_args.kwargs
        assert json.loads(json.loads(call["contents"])["original_text"])["facts"] == evidence.facts
        assert call["config"].response_json_schema == RecommendationDraft.model_json_schema()


@pytest.mark.recommendations_live
@pytest.mark.skipif(os.getenv("RUN_RECOMMENDATION_STORAGE_INTEGRATION") != "1", reason="Live recommendation writes with mocked Gemini are opt-in")
def test_live_storage_round_trip_with_mocked_gemini(draft):
    store = BigQueryService(config.get_bigquery_settings())
    now = datetime.now(timezone.utc)
    request_count_sql = f"SELECT COUNT(*) AS total FROM `{store.table_id('citizen_requests')}`"
    before = store.execute_query(request_count_sql)[0]["total"]
    service = RecommendationService(store)
    gemini = MagicMock()
    gemini.settings.timeout_seconds = 30
    mock_draft = draft.model_copy(update={"limitations": ["Synthetic integration test with mocked Gemini output; not a live model recommendation."]})
    gemini.generate_structured = AsyncMock(return_value=mock_draft)
    app = create_app(cors_origins=[])
    app.dependency_overrides[recommendation_api.get_recommendation_service] = lambda: service
    app.dependency_overrides[recommendation_api.get_recommendation_agent] = lambda: RecommendationAgent(gemini)
    try:
        hotspots = HotspotService(store, HotspotSettings(request_threshold=0)).detect(as_of=now)
        scores = PriorityService(store).refresh(hotspots)
        selected = next(row for row in scores if row.category == "Healthcare" and row.scoring_status == "complete")
        with TestClient(app) as client:
            response = client.post("/api/v1/recommendations/generate", json={"hotspot_id": selected.hotspot_id})
            assert response.status_code == 201, response.text
            recommendation = response.json()
            recommendation_id = recommendation["recommendation_id"]
            detail = client.get(f"/api/v1/recommendations/{recommendation_id}")
            assert detail.status_code == 200 and detail.json() == recommendation
            listing = client.get("/api/v1/recommendations?limit=1000")
            assert listing.status_code == 200
            assert recommendation in listing.json()
            assert recommendation["evidence_snapshot"]["hotspot_id"] == selected.hotspot_id
            gemini.generate_structured.assert_awaited_once()
    finally:
        restored = HotspotService(store, config.get_hotspot_settings()).detect(as_of=now)
        PriorityService(store).refresh(restored)
    assert store.execute_query(request_count_sql)[0]["total"] == before