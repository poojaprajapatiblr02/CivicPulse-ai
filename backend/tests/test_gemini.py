import json
import logging
import asyncio
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from google import genai
from google.genai import errors, types
from google.auth.credentials import AnonymousCredentials
from google.oauth2.credentials import Credentials
from pydantic import ValidationError

from app.api.requests import get_request_agent
from app.core.config import GeminiSettings
from app.core import config
from app.main import create_app
from app.schemas.analysis import AnalyzeResponse, RequestAnalysis
from app.services.gemini_service import GeminiService, GeminiServiceError
from app.services import gemini_service

def analysis_payload(language: str = "English") -> dict:
    return {
        "language": language, "category": "Healthcare", "sub_category": "Hospital",
        "problem": "Need a nearby hospital", "location_name": None,
        "urgency": 0.7, "confidence": 0.9,
    }


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock()
    client.__enter__.return_value = client
    client.aio.__aenter__ = AsyncMock(return_value=client.aio)
    client.aio.__aexit__ = AsyncMock(return_value=False)
    client.aio.models.generate_content = AsyncMock()
    return client


@pytest.fixture
def service(mock_client: MagicMock) -> GeminiService:
    return GeminiService(
        GeminiSettings(project_id="demo-project", region="global", model="gemini-3.1-flash-lite"),
        client_factory=lambda: mock_client,
    )


@pytest.fixture
def client(service: GeminiService, request_app) -> Iterator[TestClient]:
    app = request_app
    app.dependency_overrides[get_request_agent] = lambda: service
    with TestClient(app) as test_client:
        yield test_client


def test_multilingual_analysis_preserves_text(
    client: TestClient, mock_client: MagicMock, citizen_example: tuple[str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    language, text = citizen_example
    mock_client.aio.models.generate_content.return_value = MagicMock(
        text=json.dumps(analysis_payload(language)),
    )
    original_text = "  " + text + "\n"
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        response = client.post("/api/v1/requests/analyze", json={"text": original_text})
    assert response.status_code == 201
    assert {name: response.json()[name] for name in AnalyzeResponse.model_fields} == {**analysis_payload(language), "original_text": original_text}
    assert response.json()["latitude"] is None and response.json()["longitude"] is None
    call = mock_client.aio.models.generate_content.call_args
    assert json.loads(call.kwargs["contents"])["original_text"] == original_text
    assert call.kwargs["config"].response_mime_type == "application/json"
    assert call.kwargs["config"].response_json_schema == RequestAnalysis.model_json_schema()
    assert response.headers["X-Request-ID"] in caplog.text
    assert text not in caplog.text
    mock_client.aio.__aexit__.assert_awaited_once()


@pytest.mark.parametrize("body", [{}, {"text": ""}, {"text": " \n\t"}, {"text": 123}, {"text": "x" * 5001}, {"text": "hello", "latitude": 12}])
def test_invalid_input_never_calls_model(client: TestClient, mock_client: MagicMock, body: dict) -> None:
    assert client.post("/api/v1/requests/analyze", json=body).status_code == 422
    mock_client.aio.models.generate_content.assert_not_called()


@pytest.mark.parametrize("model_text", [None, "", "not json", "```json\n{}\n```", "{}", "[]", "null"])
def test_malformed_output_is_safe(client: TestClient, mock_client: MagicMock, model_text: str | None) -> None:
    mock_client.aio.models.generate_content.return_value = MagicMock(text=model_text)
    response = client.post("/api/v1/requests/analyze", json={"text": "We need a hospital"})
    assert response.status_code == 502
    assert response.json() == {"detail": "Gemini returned an invalid analysis. Please retry."}


@pytest.mark.parametrize("change", [
    {"urgency": 1.1}, {"confidence": -0.1}, {"confidence": "0.9"},
    {"language": "French"}, {"category": "Finance"}, {"latitude": 12.95},
    {"original_text": "changed by model"}, {"problem": ""},
])
def test_invalid_model_fields_rejected(client: TestClient, mock_client: MagicMock, change: dict) -> None:
    mock_client.aio.models.generate_content.return_value = MagicMock(text=json.dumps({**analysis_payload(), **change}))
    assert client.post("/api/v1/requests/analyze", json={"text": "hospital"}).status_code == 502


def test_post_cors(client: TestClient) -> None:
    response = client.options("/api/v1/requests/analyze", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


@pytest.mark.parametrize(("error", "status"), [
    (TimeoutError("private text"), 504),
    (httpx.ReadTimeout("private text"), 504),
    (RuntimeError("private text"), 503),
    (errors.ClientError(403, {"error": {"message": "private text"}}), 503),
    (errors.ClientError(429, {"error": {"message": "private text"}}), 503),
    (errors.ServerError(504, {"error": {"message": "private text"}}), 504),
])
def test_upstream_errors_redacted(
    client: TestClient, mock_client: MagicMock, error: Exception, status: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    mock_client.aio.models.generate_content.side_effect = error
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        response = client.post("/api/v1/requests/analyze", json={"text": "Need a hospital"})
    assert response.status_code == status
    assert "private text" not in response.text + caplog.text
    assert response.headers["X-Request-ID"] in caplog.text
    mock_client.aio.__aexit__.assert_awaited_once()


def test_application_deadline_cancels_pending_call(service: GeminiService, mock_client: MagicMock) -> None:
    service.settings.timeout_seconds = 0.01

    async def pending(**kwargs):
        await asyncio.Future()

    mock_client.aio.models.generate_content.side_effect = pending
    with pytest.raises(GeminiServiceError) as captured:
        asyncio.run(service.analyze("Need a hospital", request_id="test-deadline"))
    assert captured.value.status_code == 504
    mock_client.aio.__aexit__.assert_awaited_once()


@pytest.mark.parametrize(("place", "status"), [("Demo Village", 201), ("Invented Town", 502)])
def test_location_must_appear_in_input(client: TestClient, mock_client: MagicMock, place: str, status: int) -> None:
    mock_client.aio.models.generate_content.return_value = MagicMock(text=json.dumps({
        **analysis_payload(), "location_name": place,
    }))
    response = client.post("/api/v1/requests/analyze", json={"text": "Demo Village needs a hospital"})
    assert response.status_code == status


def test_unsupported_language(client: TestClient, mock_client: MagicMock) -> None:
    mock_client.aio.models.generate_content.return_value = MagicMock(text=json.dumps(analysis_payload("Unsupported")))
    assert client.post("/api/v1/requests/analyze", json={"text": "Bonjour"}).status_code == 422


def test_blank_analysis_rejected(client: TestClient, mock_client: MagicMock) -> None:
    mock_client.aio.models.generate_content.return_value = MagicMock(text=json.dumps({**analysis_payload(), "problem": "  "}))
    assert client.post("/api/v1/requests/analyze", json={"text": "hospital"}).status_code == 502


def test_adc_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    credentials = AnonymousCredentials()
    adc = MagicMock(return_value=(credentials, "ignored-default-project"))
    factory = MagicMock()
    monkeypatch.setattr(gemini_service.google.auth, "default", adc)
    monkeypatch.setattr(gemini_service.genai, "Client", factory)
    settings = GeminiSettings(project_id="demo-project", region="global", model="gemini-3.1-flash-lite")
    service = GeminiService(settings)
    service._create_client()
    adc.assert_called_once_with(scopes=["https://www.googleapis.com/auth/cloud-platform"], quota_project_id="demo-project")
    arguments = factory.call_args.kwargs
    assert arguments["vertexai"] is True
    assert arguments["credentials"] is credentials
    assert arguments["project"] == "demo-project"
    assert arguments["location"] == "global"
    assert "api_key" not in arguments
    assert arguments["http_options"].timeout == 30000
    assert arguments["http_options"].retry_options.attempts == 1


def test_environment_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda path: None)
    for key, value in {"GCP_PROJECT_ID": "demo-project", "GCP_REGION": "global",
                       "GEMINI_MODEL": "gemini-3.1-flash-lite", "GEMINI_TIMEOUT_SECONDS": "15"}.items():
        monkeypatch.setenv(key, value)
    settings = config.get_gemini_settings()
    assert settings.region == "global"
    assert settings.timeout_seconds == 15
    assert settings.model == "gemini-3.1-flash-lite"


@pytest.mark.parametrize("change", [{"project_id": ""}, {"region": ""}, {"model": ""}, {"timeout_seconds": 0}, {"timeout_seconds": 121}])
def test_invalid_settings(change: dict) -> None:
    with pytest.raises(ValidationError):
        GeminiSettings(**{"project_id": "demo-project", "region": "global", "model": "gemini-3.1-flash-lite", **change})


def test_missing_config_returns_safe_error(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda path: None)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    with TestClient(create_app(cors_origins=[])) as test_client:
        with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
            response = test_client.post("/api/v1/requests/analyze", json={"text": "hospital"})
    assert response.status_code == 503
    assert response.headers["X-Request-ID"] in caplog.text
    assert "hospital" not in caplog.text


def test_dependency_creates_service_without_authentication(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import requests

    settings = GeminiSettings(project_id="demo-project", region="global", model="gemini-3.1-flash-lite")
    monkeypatch.setattr(requests, "get_gemini_settings", lambda: settings)
    assert requests.get_gemini_service(MagicMock()).settings is settings


def test_installed_sdk_vertex_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-unused-key")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-unused-key")
    requests_seen = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        return httpx.Response(200, json={"candidates": [{
            "content": {"role": "model", "parts": [{"text": json.dumps(analysis_payload())}]},
            "finishReason": "STOP",
        }]})

    transport = httpx.MockTransport(respond)

    def factory() -> genai.Client:
        return genai.Client(
            vertexai=True, project="demo-project", location="global", credentials=Credentials(token="fake-test-token"),
            http_options=types.HttpOptions(
                api_version="v1", httpx_client=httpx.Client(transport=transport),
                httpx_async_client=httpx.AsyncClient(transport=transport),
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    service = GeminiService(
        GeminiSettings(project_id="demo-project", region="global", model="gemini-3.1-flash-lite"),
        client_factory=factory,
    )
    result = asyncio.run(service.analyze("Need a hospital", request_id="sdk-test"))
    assert result.category == "Healthcare"
    assert len(requests_seen) == 1
    request = requests_seen[0]
    assert request.url.host == "aiplatform.googleapis.com"
    assert "/projects/demo-project/locations/global/publishers/google/models/gemini-3.1-flash-lite:generateContent" in request.url.path
    assert "x-goog-api-key" not in request.headers
    assert "key" not in request.url.params
    body = json.loads(request.content)
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["responseJsonSchema"]["additionalProperties"] is False