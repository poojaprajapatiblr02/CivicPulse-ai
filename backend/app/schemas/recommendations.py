from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.schemas.analysis import Category
from app.schemas.priorities import InfrastructureInput

EvidenceKey = Literal[
    "request_count", "population", "available_capacity", "required_capacity", "capacity_gap",
    "infrastructure_gap_score", "priority_score", "investment_inr", "estimated_need_inr",
    "investment_gap_inr", "investment_gap_score", "asset_count", "average_distance_km", "financial_year",
]


class GenerateRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hotspot_id: UUID


class EvidenceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    hotspot_id: str
    hotspot_created_at: AwareDatetime
    category: Category
    location_name: str
    district: str
    facts: dict[EvidenceKey, str]
    limitations: list[str]


class RecommendationText(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    recommended_intervention: str = Field(min_length=1, max_length=500)
    reasoning: list[str] = Field(min_length=1, max_length=8)
    expected_impact: str = Field(min_length=1, max_length=1000)
    confidence: float = Field(ge=0, le=1)
    limitations: list[str] = Field(min_length=1, max_length=16)

    @field_validator("recommended_intervention", "expected_impact", "reasoning", "limitations")
    @classmethod
    def nonblank_bounded_text(cls, value: str | list[str]) -> str | list[str]:
        values = [value] if isinstance(value, str) else value
        if any(not text.strip() or len(text) > 2000 for text in values):
            raise ValueError("Recommendation text must be nonblank and bounded")
        return value


class RecommendationDraft(RecommendationText):
    evidence_keys: list[EvidenceKey] = Field(min_length=3, max_length=14)


class RecommendationResult(RecommendationText):
    evidence: list[str] = Field(min_length=3, max_length=14)
    limitations: list[str] = Field(min_length=1, max_length=24)


class StoredRecommendation(RecommendationResult):
    recommendation_id: str
    hotspot_id: str
    created_at: AwareDatetime
    evidence_snapshot: EvidenceSnapshot


class RecommendationState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str
    evidence_snapshot: EvidenceSnapshot
    draft: RecommendationDraft | None = None
    result: RecommendationResult | None = None


class RecommendationInfrastructure(InfrastructureInput):
    asset_type: str = Field(min_length=1, max_length=100)
    asset_count: int = Field(ge=0)
    average_distance_km: float | None = Field(ge=0)