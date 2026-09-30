from datetime import datetime
from typing import Any

from google.cloud import bigquery

from app.schemas.bigquery import DATA_SOURCE
from app.schemas.priorities import PriorityRecord
from app.schemas.recommendations import EvidenceSnapshot, RecommendationInfrastructure, RecommendationResult, StoredRecommendation
from app.services.bigquery_service import BigQueryService
from app.services.gap_analysis_service import unique_records
from app.services.priority_service import PriorityService

INCOMPLETE = "Evidence is incomplete or changed. Run hotspot detection before generating a recommendation."


class RecommendationEvidenceError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def build_evidence(priority: PriorityRecord, infrastructure: list[dict[str, Any]]) -> EvidenceSnapshot:
    required = (
        priority.priority_score, priority.infrastructure_gap_score, priority.available_capacity,
        priority.required_capacity, priority.capacity_gap, priority.investment_inr,
        priority.estimated_need_inr, priority.investment_gap_inr, priority.investment_gap_score,
        priority.capacity_unit, priority.financial_year,
    )
    if priority.scoring_status != "complete" or any(value is None for value in required):
        raise RecommendationEvidenceError(409, INCOMPLETE)
    assets = unique_records([RecommendationInfrastructure.model_validate(row) for row in infrastructure])
    if len(assets) != 1:
        raise RecommendationEvidenceError(409, INCOMPLETE)
    asset = assets[0]
    if (asset.district, asset.location_name, asset.category, asset.available_capacity, asset.required_capacity, asset.capacity_unit) != (
        priority.district, priority.location_name, priority.category, priority.available_capacity, priority.required_capacity, priority.capacity_unit,
    ):
        raise RecommendationEvidenceError(409, INCOMPLETE)
    facts = {
        "request_count": f"Citizen request count: {priority.request_count} requests",
        "population": f"Locality population proxy: {priority.affected_population} people",
        "available_capacity": f"Available service capacity: {priority.available_capacity} {priority.capacity_unit}",
        "required_capacity": f"Required service capacity: {priority.required_capacity} {priority.capacity_unit}",
        "capacity_gap": f"Unmet service capacity: {priority.capacity_gap} {priority.capacity_unit}",
        "infrastructure_gap_score": f"Infrastructure gap score: {priority.infrastructure_gap_score} out of 100",
        "priority_score": f"Development priority score: {priority.priority_score} out of 100",
        "investment_inr": f"Recorded government investment: {priority.investment_inr} INR",
        "estimated_need_inr": f"Recorded estimated funding need: {priority.estimated_need_inr} INR",
        "investment_gap_inr": f"Unmet recorded funding need: {priority.investment_gap_inr} INR",
        "investment_gap_score": f"Investment gap score: {priority.investment_gap_score} out of 100",
        "financial_year": f"Investment financial year: {priority.financial_year}",
        "asset_count": f"Recorded infrastructure asset count: {asset.asset_count} {asset.asset_type}",
    }
    limitations = [
        "Synthetic demonstration data; not verified government statistics.",
        "Population is a locality-level proxy, not a verified affected-person count.",
        "No project cost, delivery timeline, or quantified impact has been established.",
        "Advisory output requires field assessment and does not authorize funding or construction.",
        "Confidence is an uncalibrated model estimate, not a measured probability.",
    ]
    if asset.average_distance_km is not None:
        facts["average_distance_km"] = f"Recorded average service distance: {asset.average_distance_km} km"
    else:
        limitations.append("Average service distance is unavailable in the source dataset.")
    return EvidenceSnapshot(
        hotspot_id=priority.hotspot_id, hotspot_created_at=priority.created_at, category=priority.category,
        location_name=priority.location_name, district=priority.district, facts=facts, limitations=limitations,
    )


class RecommendationService:
    def __init__(self, store: BigQueryService) -> None:
        self.store = store

    def get_evidence(self, hotspot_id: str) -> EvidenceSnapshot:
        priorities = PriorityService(self.store).list_results(hotspot_id=hotspot_id, limit=1)
        if not priorities:
            exists = self.store.execute_query(
                f"SELECT hotspot_id FROM `{self.store.table_id('hotspots')}` WHERE hotspot_id = @hotspot_id LIMIT 1",
                [bigquery.ScalarQueryParameter("hotspot_id", "STRING", hotspot_id)],
            )
            if not exists:
                raise RecommendationEvidenceError(404, "Hotspot not found.")
            raise RecommendationEvidenceError(409, INCOMPLETE)
        priority = priorities[0]
        columns = ", ".join(RecommendationInfrastructure.model_fields)
        rows = self.store.execute_query(
            f"SELECT {columns} FROM `{self.store.table_id('infrastructure')}` "
            "WHERE district = @district AND location_name = @location AND category = @category AND data_source = @source",
            [bigquery.ScalarQueryParameter("district", "STRING", priority.district),
             bigquery.ScalarQueryParameter("location", "STRING", priority.location_name),
             bigquery.ScalarQueryParameter("category", "STRING", priority.category),
             bigquery.ScalarQueryParameter("source", "STRING", DATA_SOURCE)],
        )
        return build_evidence(priority, rows)

    def save(
        self, result: RecommendationResult, snapshot: EvidenceSnapshot, *, recommendation_id: str, created_at: datetime,
    ) -> StoredRecommendation:
        current = self.store.execute_query(
            f"SELECT hotspot_id FROM `{self.store.table_id('hotspots')}` "
            "WHERE hotspot_id = @hotspot_id AND created_at = @snapshot_at LIMIT 1",
            [bigquery.ScalarQueryParameter("hotspot_id", "STRING", snapshot.hotspot_id),
             bigquery.ScalarQueryParameter("snapshot_at", "TIMESTAMP", snapshot.hotspot_created_at)],
        )
        if not current:
            raise RecommendationEvidenceError(409, INCOMPLETE)
        stored = StoredRecommendation(
            **result.model_dump(), recommendation_id=recommendation_id,
            hotspot_id=snapshot.hotspot_id, created_at=created_at, evidence_snapshot=snapshot,
        )
        row = {**stored.model_dump(mode="json"), "evidence_snapshot": snapshot.model_dump_json()}
        self.store.insert_records("recommendations", [row])
        return stored

    def _deserialize(self, row: dict[str, Any]) -> StoredRecommendation:
        return StoredRecommendation.model_validate({
            **row, "evidence_snapshot": EvidenceSnapshot.model_validate_json(row["evidence_snapshot"]),
        })

    def list_recommendations(self, *, limit: int = 100) -> list[StoredRecommendation]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        rows = self.store.execute_query(
            f"SELECT * FROM `{self.store.table_id('recommendations')}` ORDER BY created_at DESC, recommendation_id LIMIT @limit",
            [bigquery.ScalarQueryParameter("limit", "INT64", limit)],
        )
        return [self._deserialize(row) for row in rows]

    def get_recommendation(self, recommendation_id: str) -> StoredRecommendation | None:
        rows = self.store.execute_query(
            f"SELECT * FROM `{self.store.table_id('recommendations')}` WHERE recommendation_id = @id LIMIT 1",
            [bigquery.ScalarQueryParameter("id", "STRING", recommendation_id)],
        )
        return self._deserialize(rows[0]) if rows else None