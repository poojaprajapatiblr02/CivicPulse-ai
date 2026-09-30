from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Language = Literal["English", "Hindi", "Kannada", "Unsupported"]
Category = Literal["Healthcare", "Education", "Roads", "Water", "Electricity", "Other"]


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(min_length=1, max_length=5000)

    @field_validator("text")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Text must not be blank")
        return value


class RequestAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    language: Language
    category: Category
    sub_category: str = Field(min_length=1, max_length=100)
    problem: str = Field(min_length=1, max_length=1000)
    location_name: str | None = Field(max_length=200)
    urgency: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)

    @field_validator("sub_category", "problem", "location_name")
    @classmethod
    def reject_blank_fields(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Analysis fields must not be blank")
        return value


class AnalyzeResponse(RequestAnalysis):
    original_text: str