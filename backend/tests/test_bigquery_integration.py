"""Explicit opt-in live validation; no cloud access during normal unit tests."""

import csv
import os
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.dashboard import get_bigquery_service
from app.core.config import get_bigquery_settings
from app.main import create_app
from app.services.bigquery_service import BigQueryService
from app.schemas.bigquery import CATEGORIES

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_BIGQUERY_INTEGRATION") != "1", reason="Live BigQuery validation is opt-in"),
]


def test_live_summary_matches_csv() -> None:
    data_dir = Path(__file__).resolve().parents[2] / "data/synthetic"
    tables = {}
    for name in ("citizen_requests", "demographics", "infrastructure", "government_investments"):
        with (data_dir / f"{name}.csv").open(encoding="utf-8", newline="") as source:
            tables[name] = list(csv.DictReader(source))
    service = BigQueryService(get_bigquery_settings())
    app = create_app(cors_origins=[])
    app.dependency_overrides[get_bigquery_service] = lambda: service
    with TestClient(app) as client:
        response = client.get("/api/v1/dashboard/summary")
    assert response.status_code == 200
    result = response.json()
    counts = service.execute_query(f"""
        SELECT category, COUNT(*) AS total_count,
               COUNTIF(STARTS_WITH(request_id, 'SYN-REQ-')) AS seed_count
        FROM `{service.table_id('citizen_requests')}` GROUP BY category
    """)
    assert sum(row["seed_count"] for row in counts) == len(tables["citizen_requests"])
    assert {row["category"]: row["seed_count"] for row in counts if row["seed_count"]} == dict(Counter(row["category"] for row in tables["citizen_requests"]))
    assert result["total_requests"] == sum(row["total_count"] for row in counts)
    expected_counts = dict.fromkeys(CATEGORIES, 0)
    expected_counts.update({row["category"]: row["total_count"] for row in counts})
    assert result["requests_by_category"] == expected_counts
    assert result["total_population"] == sum(int(row["population"]) for row in tables["demographics"])
    assert result["infrastructure_records"] == len(tables["infrastructure"])
    assert Decimal(result["total_investment"]) == sum(Decimal(row["investment_inr"]) for row in tables["government_investments"])
    assert result["data_source"] == "SYNTHETIC / DEMO DATA"
    requests = service.query_records("citizen_requests", category="Water", limit=5)
    assert requests and all(row["category"] == "Water" for row in requests)