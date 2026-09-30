import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from langsmith import tracing_context
from langsmith.run_helpers import get_tracing_context
from pydantic import ValidationError

from app.agents.request_agent import RequestAgent, validate_analysis
from app.api.requests import get_gemini_service
from app.schemas.analysis import AnalyzeResponse
from app.schemas.request_agent import ClassificationResult, EntityResult, LanguageResult, LocationResult, RequestAgentState, UrgencyResult
from app.services.gemini_service import GeminiServiceError


@pytest.fixture
def service() -> MagicMock:
    service = MagicMock()
    service.settings.timeout_seconds = 30
    service.generate_structured = AsyncMock()
    return service


def configure_outputs(service: MagicMock, language: str = "English", category: str = "Healthcare", location: str | None = None) -> None:
    outputs = {
        "LanguageResult": {"language": language, "confidence": 0.95},
        "ClassificationResult": {"category": category, "sub_category": "Hospital", "confidence": 0.93},
        "EntityResult": {"problem": "Hospital is too far", "confidence": 0.94},
        "LocationResult": {"location_name": location, "confidence": 0.96},
        "UrgencyResult": {"urgency": 0.78, "confidence": 0.97},
    }

    async def generate(**kwargs):
        model = kwargs["response_model"]
        return model.model_validate(outputs[model.__name__])

    service.generate_structured.side_effect = generate


def test_multilingual_graph(service: MagicMock, citizen_example: tuple[str, str], caplog: pytest.LogCaptureFixture, request_app) -> None:
    language, text = citizen_example
    configure_outputs(service, language)
    original = "  " + text + "\n"
    app = request_app
    app.dependency_overrides[get_gemini_service] = lambda: service
    with TestClient(app) as client, caplog.at_level(logging.INFO, logger="uvicorn.error"):
        response = client.post("/api/v1/requests/analyze", json={"text": original})
    assert response.status_code == 201
    assert {name: response.json()[name] for name in AnalyzeResponse.model_fields} == {
        "language": language, "category": "Healthcare", "sub_category": "Hospital",
        "problem": "Hospital is too far", "location_name": None, "urgency": 0.78,
        "confidence": 0.93, "original_text": original,
    }
    calls = service.generate_structured.call_args_list
    assert [call.kwargs["response_model"].__name__ for call in calls] == [
        "LanguageResult", "ClassificationResult", "EntityResult", "LocationResult", "UrgencyResult",
    ]
    assert all(call.kwargs["text"] == original for call in calls)
    entries = [json.loads(record.message) for record in caplog.records if '"operation": "request_agent_node"' in record.message]
    assert [entry["node"] for entry in entries] == [
        "language_detection", "classification", "entity_extraction", "location_extraction", "urgency_analysis", "validation",
    ]
    assert all(entry["request_id"] == response.headers["X-Request-ID"] for entry in entries)
    assert all(entry["success"] for entry in entries)
    assert text not in caplog.text


def test_unknown_category(service: MagicMock) -> None:
    configure_outputs(service, category="Other")
    result = asyncio.run(RequestAgent(service).analyze("Please arrange a festival", request_id="other"))
    assert result.category == "Other"


@pytest.mark.parametrize(("location", "expected"), [(None, None), ("Invented Town", None), ("Demo Village", "Demo Village")])
def test_location_grounding(service: MagicMock, location: str | None, expected: str | None) -> None:
    configure_outputs(service, location=location)
    result = asyncio.run(RequestAgent(service).analyze("Demo Village needs a hospital", request_id="location"))
    assert result.location_name == expected
    assert "latitude" not in result.model_dump()


def test_malformed_llm_stops_graph(service: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
    service.generate_structured.side_effect = GeminiServiceError(502, "Gemini returned an invalid analysis. Please retry.")
    with caplog.at_level(logging.INFO, logger="uvicorn.error"), pytest.raises(GeminiServiceError) as error:
        asyncio.run(RequestAgent(service).analyze("hospital", request_id="failure"))
    assert error.value.status_code == 502
    assert service.generate_structured.call_count == 1
    assert '"success": false' in caplog.text
    assert '"node": "classification"' not in caplog.text


def test_unsupported_language_stops_before_classification(service: MagicMock) -> None:
    configure_outputs(service, language="Unsupported")
    with pytest.raises(GeminiServiceError) as error:
        asyncio.run(RequestAgent(service).analyze("Bonjour", request_id="unsupported"))
    assert error.value.status_code == 422
    assert service.generate_structured.call_count == 1


@pytest.mark.parametrize(("failure", "status"), [
    (GeminiServiceError(504, "Gemini analysis timed out. Please retry."), 504),
    (RuntimeError("private upstream data"), 503),
    ({"problem": " " , "confidence": 0.9}, 502),
])
def test_later_agent_failure_is_safe(service: MagicMock, failure: object, status: int, caplog: pytest.LogCaptureFixture, request_app) -> None:
    service.generate_structured.side_effect = [
        LanguageResult(language="English", confidence=0.9),
        ClassificationResult(category="Healthcare", sub_category="Hospital", confidence=0.9),
        failure,
    ]
    app = request_app
    app.dependency_overrides[get_gemini_service] = lambda: service
    with TestClient(app) as client, caplog.at_level(logging.INFO, logger="uvicorn.error"):
        response = client.post("/api/v1/requests/analyze", json={"text": "hospital"})
    assert response.status_code == status
    assert service.generate_structured.call_count == 3
    assert "private upstream data" not in response.text + caplog.text
    assert '"node": "entity_extraction"' in caplog.text
    assert '"node": "location_extraction"' not in caplog.text


def test_external_tracing_disabled_even_when_parent_enabled(service: MagicMock) -> None:
    configure_outputs(service)
    generate = service.generate_structured.side_effect

    async def check_tracing(**kwargs):
        assert get_tracing_context()["enabled"] is False
        return await generate(**kwargs)

    service.generate_structured.side_effect = check_tracing
    trace_client = MagicMock()
    with tracing_context(enabled=True, client=trace_client):
        asyncio.run(RequestAgent(service).analyze("hospital", request_id="privacy"))
        assert get_tracing_context()["enabled"] is True
    trace_client.create_run.assert_not_called()
    trace_client.update_run.assert_not_called()


@pytest.mark.parametrize(("model", "payload"), [
    (LanguageResult, {"language": "French", "confidence": 0.9}),
    (ClassificationResult, {"category": "Healthcare", "sub_category": " ", "confidence": 0.9}),
    (EntityResult, {"problem": "hospital", "confidence": "0.9"}),
    (EntityResult, {"problem": "hospital", "confidence": float("nan")}),
    (LocationResult, {"location_name": None, "confidence": 0.9, "latitude": 12.0}),
    (UrgencyResult, {"urgency": 1.1, "confidence": 0.9}),
])
def test_agent_outputs_are_strict(model: type, payload: dict) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_incomplete_state_rejected() -> None:
    with pytest.raises(GeminiServiceError) as error:
        asyncio.run(validate_analysis(RequestAgentState(text="hospital", request_id="incomplete")))
    assert error.value.status_code == 502


def test_total_deadline(service: MagicMock) -> None:
    agent = RequestAgent(service)
    agent.graph = MagicMock()
    agent.graph.ainvoke = AsyncMock(side_effect=TimeoutError)
    with pytest.raises(GeminiServiceError) as error:
        asyncio.run(agent.analyze("hospital", request_id="timeout"))
    assert error.value.status_code == 504


def test_graph_cancellation_propagates(service: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
    async def cancel_running_graph() -> None:
        started = asyncio.Event()

        async def pending_generation(**kwargs):
            started.set()
            await asyncio.Future()

        service.generate_structured.side_effect = pending_generation
        task = asyncio.create_task(RequestAgent(service).analyze("hospital", request_id="cancelled"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        asyncio.run(cancel_running_graph())
    assert '"error_type": "Cancelled"' in caplog.text


@pytest.mark.parametrize(("output", "status"), [
    ({"text": "hospital", "request_id": "invalid"}, 502),
    ({"unknown": "field"}, 502),
    (RuntimeError("private graph details"), 503),
])
def test_invalid_graph_result_is_safe(service: MagicMock, output: object, status: int) -> None:
    agent = RequestAgent(service)
    agent.graph = MagicMock()
    agent.graph.ainvoke = AsyncMock(side_effect=[output])
    with pytest.raises(GeminiServiceError) as error:
        asyncio.run(agent.analyze("hospital", request_id="invalid"))
    assert error.value.status_code == status
    assert "private graph details" not in error.value.detail