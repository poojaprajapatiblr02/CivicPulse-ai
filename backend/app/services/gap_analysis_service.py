from decimal import Decimal
from typing import Any, TypeVar

from google.cloud import bigquery
from pydantic import BaseModel

from app.schemas.bigquery import DATA_SOURCE
from app.schemas.hotspots import Hotspot
from app.schemas.priorities import DemographicInput, GapEvidence, InfrastructureInput, InvestmentInput
from app.services.bigquery_service import BigQueryService

SourceModel = TypeVar("SourceModel", bound=BaseModel)


def unique_records(records: list[SourceModel]) -> list[SourceModel]:
    result = []
    for record in records:
        if record not in result:
            result.append(record)
    return result


def analyze_gaps(
    hotspots: list[Hotspot], demographics: list[dict[str, Any]],
    infrastructure: list[dict[str, Any]], investments: list[dict[str, Any]],
) -> dict[str, GapEvidence]:
    people = [DemographicInput.model_validate(record) for record in demographics]
    assets = [InfrastructureInput.model_validate(record) for record in infrastructure]
    funding = [InvestmentInput.model_validate(record) for record in investments]
    results = {}
    for hotspot in hotspots:
        evidence = GapEvidence()
        issues = []
        population_matches = unique_records([record for record in people if (
            record.district, record.location_name
        ) == (hotspot.district, hotspot.location_name)])
        key = (hotspot.district, hotspot.location_name, hotspot.category)
        asset_matches = unique_records([record for record in assets if (
            record.district, record.location_name, record.category
        ) == key])
        funding_matches = unique_records([record for record in funding if (
            record.district, record.location_name, record.category
        ) == key])
        if len(population_matches) == 1:
            evidence.vulnerability_index = population_matches[0].vulnerability_index
        else:
            issues.append("missing_or_ambiguous_demographics")
        if len(asset_matches) == 1:
            asset = asset_matches[0]
            evidence.available_capacity = asset.available_capacity
            evidence.required_capacity = asset.required_capacity
            evidence.capacity_unit = asset.capacity_unit
            evidence.capacity_gap = float(max(Decimal(0), Decimal(str(asset.required_capacity)) - Decimal(str(asset.available_capacity))))
        else:
            issues.append("missing_or_ambiguous_infrastructure")
        if funding_matches:
            latest_year = max(record.financial_year for record in funding_matches)
            funding_matches = [record for record in funding_matches if record.financial_year == latest_year]
        if len(funding_matches) == 1:
            investment = funding_matches[0]
            evidence.investment_inr = investment.investment_inr
            evidence.estimated_need_inr = investment.estimated_need_inr
            evidence.financial_year = investment.financial_year
            evidence.investment_gap_inr = max(Decimal(0), investment.estimated_need_inr - investment.investment_inr)
        else:
            issues.append("missing_or_ambiguous_investment")
        evidence.data_issues = "; ".join(issues) or None
        results[hotspot.hotspot_id] = evidence
    return results


class GapAnalysisService:
    def __init__(self, store: BigQueryService) -> None:
        self.store = store

    def analyze(self, hotspots: list[Hotspot]) -> dict[str, GapEvidence]:
        if not hotspots:
            return {}
        sources = []
        for table, model in (("demographics", DemographicInput), ("infrastructure", InfrastructureInput), ("government_investments", InvestmentInput)):
            columns = ", ".join(model.model_fields)
            sources.append(self.store.execute_query(
                f"SELECT {columns} FROM `{self.store.table_id(table)}` WHERE data_source = @source",
                [bigquery.ScalarQueryParameter("source", "STRING", DATA_SOURCE)],
            ))
        return analyze_gaps(hotspots, *sources)