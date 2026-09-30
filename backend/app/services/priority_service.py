from decimal import Decimal, ROUND_HALF_UP

from google.cloud import bigquery

from app.schemas.hotspots import Hotspot
from app.schemas.priorities import GapEvidence, PriorityRecord, ScoreComponents
from app.services.bigquery_service import BigQueryService
from app.services.gap_analysis_service import GapAnalysisService

WEIGHTS = {
    "demand_score": Decimal("0.30"),
    "infrastructure_gap_score": Decimal("0.20"),
    "population_impact_score": Decimal("0.15"),
    "vulnerability_score": Decimal("0.15"),
    "urgency_score": Decimal("0.10"),
    "investment_gap_score": Decimal("0.10"),
}


def rounded_score(value: Decimal) -> float:
    return float(min(Decimal(100), max(Decimal(0), value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def normalized_score(numerator: float | int | Decimal | None, denominator: float | int | Decimal | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    return rounded_score(Decimal(str(numerator)) / Decimal(str(denominator)) * 100) if denominator else 0.0


def weighted_priority(scores: ScoreComponents) -> float | None:
    values = scores.model_dump()
    if any(value is None for value in values.values()):
        return None
    return rounded_score(sum((Decimal(str(values[name])) * weight for name, weight in WEIGHTS.items()), Decimal(0)))


def score_hotspots(hotspots: list[Hotspot], gaps: dict[str, GapEvidence]) -> list[PriorityRecord]:
    if not hotspots:
        return []
    max_requests = max(hotspot.request_count for hotspot in hotspots)
    max_population = max(hotspot.affected_population for hotspot in hotspots)
    results = []
    for hotspot in sorted(hotspots, key=lambda row: row.hotspot_id):
        evidence = gaps.get(hotspot.hotspot_id, GapEvidence(data_issues="missing_source_data"))
        scores = ScoreComponents(
            demand_score=normalized_score(hotspot.request_count, max_requests),
            infrastructure_gap_score=normalized_score(evidence.capacity_gap, evidence.required_capacity),
            population_impact_score=normalized_score(hotspot.affected_population, max_population),
            vulnerability_score=normalized_score(evidence.vulnerability_index, 1),
            urgency_score=normalized_score(hotspot.average_urgency, 1),
            investment_gap_score=normalized_score(evidence.investment_gap_inr, evidence.estimated_need_inr),
        )
        priority = weighted_priority(scores)
        results.append(PriorityRecord(
            **hotspot.model_dump(), **evidence.model_dump(), **scores.model_dump(),
            priority_score=priority, max_request_count=max_requests, max_population=max_population,
            scoring_status="complete" if priority is not None else "insufficient_data",
        ))
    return results


class PriorityService:
    def __init__(self, store: BigQueryService) -> None:
        self.store = store

    def refresh(self, hotspots: list[Hotspot]) -> list[PriorityRecord]:
        evidence = GapAnalysisService(self.store).analyze(hotspots)
        results = score_hotspots(hotspots, evidence)
        self.store.replace_snapshot("infrastructure_gaps", [record.model_dump(mode="json") for record in results])
        return results

    def list_results(self, *, ranked: bool = False, limit: int = 1000, hotspot_id: str | None = None) -> list[PriorityRecord]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        columns = ", ".join(f"gaps.{name}" for name in PriorityRecord.model_fields)
        order = "gaps.priority_score DESC NULLS LAST, gaps.hotspot_id" if ranked else "gaps.hotspot_id"
        parameters = [bigquery.ScalarQueryParameter("limit", "INT64", limit)]
        hotspot_filter = ""
        if hotspot_id is not None:
            hotspot_filter = "AND gaps.hotspot_id = @hotspot_id "
            parameters.append(bigquery.ScalarQueryParameter("hotspot_id", "STRING", hotspot_id))
        rows = self.store.execute_query(
            f"SELECT {columns} FROM `{self.store.table_id('infrastructure_gaps')}` AS gaps "
            f"WHERE EXISTS (SELECT 1 FROM `{self.store.table_id('hotspots')}` AS snapshot "
            "WHERE snapshot.hotspot_id = gaps.hotspot_id AND snapshot.created_at = gaps.created_at) "
            f"{hotspot_filter}"
            f"ORDER BY {order} LIMIT @limit",
            parameters,
        )
        return [PriorityRecord.model_validate(row) for row in rows]