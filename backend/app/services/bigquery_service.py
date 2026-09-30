import logging
from datetime import datetime
from typing import Any

from google.cloud import bigquery

from app.core.config import BigQuerySettings
from app.schemas.bigquery import CATEGORIES, DATA_SOURCE, TABLE_SCHEMAS
from app.schemas.analysis import AnalyzeResponse
from app.schemas.dashboard import DashboardSummary
from app.schemas.requests import RequestFilters, ResolvedLocation, StoredRequest

logger = logging.getLogger("uvicorn.error")


class BigQueryServiceError(RuntimeError):
    pass


class BigQueryService:
    def __init__(self, settings: BigQuerySettings, client: bigquery.Client | None = None) -> None:
        self.settings = settings
        self.client = client if client is not None else bigquery.Client(
            project=settings.project_id, location=settings.location
        )

    def table_id(self, table_name: str) -> str:
        if table_name not in TABLE_SCHEMAS:
            raise ValueError("Unsupported BigQuery table")
        return f"{self.settings.project_id}.{self.settings.dataset}.{self.settings.table_prefix}{table_name}"

    def execute_query(
        self, sql: str, parameters: list[bigquery.ScalarQueryParameter] | None = None
    ) -> list[dict[str, Any]]:
        """Execute trusted application SQL; bind all external values as parameters."""
        config = bigquery.QueryJobConfig(
            query_parameters=parameters or [], use_legacy_sql=False,
            maximum_bytes_billed=self.settings.maximum_bytes_billed,
        )
        try:
            job = self.client.query(sql, job_config=config, location=self.settings.location, timeout=30)
            return [dict(row) for row in job.result(timeout=30)]
        except Exception as error:
            logger.warning("operation=bigquery_query success=false error_type=%s", type(error).__name__)
            raise BigQueryServiceError("BigQuery operation failed") from None

    def query_records(
        self, table_name: str, *, limit: int = 100, category: str | None = None
    ) -> list[dict[str, Any]]:
        table_id = self.table_id(table_name)
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        parameters = [bigquery.ScalarQueryParameter("limit", "INT64", limit)]
        where = ""
        if category is not None:
            if table_name == "demographics":
                raise ValueError("Demographics has no category field")
            where = " WHERE category = @category"
            parameters.append(bigquery.ScalarQueryParameter("category", "STRING", category))
        return self.execute_query(f"SELECT * FROM `{table_id}`{where} LIMIT @limit", parameters)

    def insert_records(self, table_name: str, records: list[dict[str, Any]]) -> int:
        table_id = self.table_id(table_name)
        if not records:
            return 0
        config = bigquery.LoadJobConfig(
            schema=TABLE_SCHEMAS[table_name], write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            create_disposition=bigquery.CreateDisposition.CREATE_NEVER,
        )
        try:
            job = self.client.load_table_from_json(
                records, table_id, job_config=config, location=self.settings.location, timeout=30
            )
            job.result(timeout=60)
            return len(records)
        except Exception as error:
            logger.warning("operation=bigquery_insert success=false error_type=%s", type(error).__name__)
            raise BigQueryServiceError("BigQuery operation failed") from None

    def replace_snapshot(self, table_name: str, records: list[dict[str, Any]]) -> None:
        if table_name not in {"hotspots", "infrastructure_gaps"}:
            raise ValueError("Only derived snapshots may be replaced")
        table_id = self.table_id(table_name)
        if not records:
            self.execute_query(f"DELETE FROM `{table_id}` WHERE TRUE")
            return
        config = bigquery.LoadJobConfig(
            schema=TABLE_SCHEMAS[table_name], write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            create_disposition=bigquery.CreateDisposition.CREATE_NEVER,
        )
        try:
            job = self.client.load_table_from_json(
                records, table_id, job_config=config, location=self.settings.location, timeout=30,
            )
            job.result(timeout=60)
        except Exception as error:
            logger.warning("operation=derived_snapshot success=false error_type=%s", type(error).__name__)
            raise BigQueryServiceError("Snapshot persistence failed") from None

    def resolve_location(self, location_name: str) -> ResolvedLocation | None:
        table_id = self.table_id("demographics")
        rows = self.execute_query(f"""
            SELECT DISTINCT location_name, district, latitude, longitude
            FROM `{table_id}`
            WHERE LOWER(TRIM(location_name)) = LOWER(TRIM(@location_name))
              AND data_source = @data_source
            LIMIT 2
        """, [
            bigquery.ScalarQueryParameter("location_name", "STRING", location_name),
            bigquery.ScalarQueryParameter("data_source", "STRING", DATA_SOURCE),
        ])
        return ResolvedLocation.model_validate(rows[0]) if len(rows) == 1 else None

    def store_request(
        self, analysis: AnalyzeResponse, *, request_id: str, created_at: datetime
    ) -> StoredRequest:
        location = self.resolve_location(analysis.location_name) if analysis.location_name is not None else None
        resolved = location.model_dump() if location else {"district": None, "latitude": None, "longitude": None}
        stored = StoredRequest(
            **{**analysis.model_dump(), **resolved}, request_id=request_id, created_at=created_at,
        )
        self.insert_records("citizen_requests", [{**stored.model_dump(mode="json"), "data_source": DATA_SOURCE}])
        return stored

    def list_requests(
        self, *, category: str | None = None, district: str | None = None,
        language: str | None = None, limit: int = 100,
    ) -> list[StoredRequest]:
        filters = RequestFilters(category=category, district=district, language=language, limit=limit)
        clauses = []
        parameters = [bigquery.ScalarQueryParameter("limit", "INT64", filters.limit)]
        for name in ("category", "district", "language"):
            value = getattr(filters, name)
            if value is not None:
                clauses.append(f"{name} = @{name}")
                parameters.append(bigquery.ScalarQueryParameter(name, "STRING", value))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        columns = ", ".join(StoredRequest.model_fields)
        rows = self.execute_query(
            f"SELECT {columns} FROM `{self.table_id('citizen_requests')}`{where} "
            "ORDER BY created_at DESC, request_id LIMIT @limit", parameters,
        )
        return [StoredRequest.model_validate(row) for row in rows]

    def dashboard_summary(self) -> DashboardSummary:
        requests = self.table_id("citizen_requests")
        demographics = self.table_id("demographics")
        infrastructure = self.table_id("infrastructure")
        investments = self.table_id("government_investments")
        rows = self.execute_query(f"""
            SELECT
              (SELECT COUNT(*) FROM `{requests}`) AS total_requests,
              ARRAY(SELECT AS STRUCT category, COUNT(*) AS request_count
                    FROM `{requests}` GROUP BY category ORDER BY category) AS requests_by_category,
              (SELECT COALESCE(SUM(population), 0) FROM `{demographics}`) AS total_population,
              (SELECT COUNT(*) FROM `{infrastructure}`) AS infrastructure_records,
              (SELECT COALESCE(SUM(investment_inr), 0) FROM `{investments}`) AS total_investment
        """)
        row = rows[0]
        category_counts = dict.fromkeys(CATEGORIES, 0)
        category_counts.update({entry["category"]: entry["request_count"] for entry in row["requests_by_category"]})
        return DashboardSummary(**{**row, "requests_by_category": category_counts})