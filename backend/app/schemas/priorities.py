from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.analysis import Category
from app.schemas.hotspots import Hotspot


class ScoreComponents(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    demand_score: float = Field(ge=0, le=100)
    infrastructure_gap_score: float | None = Field(ge=0, le=100)
    population_impact_score: float = Field(ge=0, le=100)
    vulnerability_score: float | None = Field(ge=0, le=100)
    urgency_score: float = Field(ge=0, le=100)
    investment_gap_score: float | None = Field(ge=0, le=100)


class GapEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    available_capacity: float | None = Field(default=None, ge=0)
    required_capacity: float | None = Field(default=None, ge=0)
    capacity_gap: float | None = Field(default=None, ge=0)
    capacity_unit: str | None = None
    vulnerability_index: float | None = Field(default=None, ge=0, le=1)
    investment_inr: Decimal | None = Field(default=None, ge=0)
    estimated_need_inr: Decimal | None = Field(default=None, ge=0)
    investment_gap_inr: Decimal | None = Field(default=None, ge=0)
    financial_year: str | None = None
    data_issues: str | None = None


class PriorityRecord(Hotspot, ScoreComponents, GapEvidence):
    priority_score: float | None = Field(ge=0, le=100)
    max_request_count: int = Field(gt=0)
    max_population: int = Field(ge=0)
    scoring_status: Literal["complete", "insufficient_data"]
    scoring_version: Literal["1.0"] = "1.0"


class DemographicInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    location_name: str = Field(min_length=1)
    district: str = Field(min_length=1)
    vulnerability_index: float = Field(ge=0, le=1)


class InfrastructureInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    location_name: str = Field(min_length=1)
    district: str = Field(min_length=1)
    category: Category
    available_capacity: float = Field(ge=0)
    required_capacity: float = Field(ge=0)
    capacity_unit: str = Field(min_length=1)


class InvestmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    location_name: str = Field(min_length=1)
    district: str = Field(min_length=1)
    category: Category
    investment_inr: Decimal = Field(ge=0)
    estimated_need_inr: Decimal = Field(ge=0)
    financial_year: str = Field(pattern=r"^\d{4}-\d{2}$")
    currency: Literal["INR"]

    @field_validator("financial_year")
    @classmethod
    def consecutive_years(cls, value: str) -> str:
        if int(value[5:]) != (int(value[:4]) + 1) % 100:
            raise ValueError("Financial year must cover consecutive years")
        return value