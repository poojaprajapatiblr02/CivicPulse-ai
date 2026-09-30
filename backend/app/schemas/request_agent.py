from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.analysis import AnalyzeRequest, AnalyzeResponse, Category, Language


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, frozen=True)
    confidence: float = Field(ge=0, le=1)

    @field_validator("*", mode="after")
    @classmethod
    def reject_blank_strings(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            raise ValueError("Agent fields must not be blank")
        return value


class LanguageResult(AgentResult):
    language: Language


class ClassificationResult(AgentResult):
    category: Category
    sub_category: str = Field(min_length=1, max_length=100)


class EntityResult(AgentResult):
    problem: str = Field(min_length=1, max_length=1000)


class LocationResult(AgentResult):
    location_name: str | None = Field(max_length=200)


class UrgencyResult(AgentResult):
    urgency: float = Field(ge=0, le=1)


class RequestAgentState(AnalyzeRequest):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    request_id: str = Field(min_length=1, max_length=100)
    language_result: LanguageResult | None = None
    classification_result: ClassificationResult | None = None
    entity_result: EntityResult | None = None
    location_result: LocationResult | None = None
    urgency_result: UrgencyResult | None = None
    response: AnalyzeResponse | None = None