"""Opt-in live create/read test; retains one synthetic request and incurs model charges."""

import os
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_bigquery_settings
from app.main import create_app
from app.schemas.requests import StoredRequest
from app.services.bigquery_service import BigQueryService

pytestmark = [
    pytest.mark.requests_live,
    pytest.mark.skipif(os.getenv("RUN_REQUEST_STORAGE_INTEGRATION") != "1", reason="Live request writes are opt-in"),
]


def test_live_create_and_retrieve() -> None:
    store = BigQueryService(get_bigquery_settings())
    location = store.resolve_location("Demo Village 01")
    assert location is not None
    text = "Demo Village 01 needs a reliable drinking water supply."
    with TestClient(create_app(cors_origins=[])) as client:
        response = client.post("/api/v1/requests", json={"text": text})
        assert response.status_code == 201, response.text
        stored = StoredRequest.model_validate_json(response.text)
        assert str(UUID(stored.request_id)) == response.headers["X-Request-ID"]
        assert stored.original_text == text
        assert stored.confidence is not None
        assert stored.category == "Water" and stored.language == "English"
        assert {field: getattr(stored, field) for field in location.model_fields} == location.model_dump()
        listing = client.get("/api/v1/requests", params={
            "category": "Water", "district": location.district, "language": "English", "limit": 1000,
        })
        assert listing.status_code == 200, listing.text
        matches = [row for row in listing.json() if row["request_id"] == stored.request_id]
        assert matches == [stored.model_dump(mode="json")]
    print(f"Stored and retrieved synthetic request: {stored.request_id}")