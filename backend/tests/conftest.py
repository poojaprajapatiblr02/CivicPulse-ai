import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import UUID

from app.api.requests import get_created_at, get_request_store
from app.core.config import BigQuerySettings
from app.main import create_app
from app.services.bigquery_service import BigQueryService

CITIZEN_EXAMPLES = [
    ("English", "We need a hospital near our village."),
    ("Hindi", "हमारे गांव में अस्पताल बहुत दूर है।"),
    ("Kannada", "ನಮ್ಮ ಗ್ರಾಮದಲ್ಲಿ ಆಸ್ಪತ್ರೆ ತುಂಬಾ ದೂರದಲ್ಲಿದೆ."),
]


@pytest.fixture(params=CITIZEN_EXAMPLES, ids=[example[0] for example in CITIZEN_EXAMPLES])
def citizen_example(request: pytest.FixtureRequest) -> tuple[str, str]:
    return request.param


@pytest.fixture
def request_store() -> BigQueryService:
    store = BigQueryService(BigQuerySettings(project_id="demo-project"), client=MagicMock())
    store.client.query.return_value.result.return_value = []
    return store


@pytest.fixture
def request_app(request_store: BigQueryService, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.main.uuid4", lambda: UUID("11111111-1111-4111-8111-111111111111"))
    app = create_app(cors_origins=["http://localhost:5173"])
    app.dependency_overrides[get_request_store] = lambda: request_store
    app.dependency_overrides[get_created_at] = lambda: datetime(2026, 9, 20, tzinfo=timezone.utc)
    return app