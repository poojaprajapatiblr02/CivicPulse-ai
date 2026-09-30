from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.analysis import AnalyzeResponse, Category

SupportedLanguage = Literal["English", "Hindi", "Kannada"]


class ResolvedLocation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    location_name: str = Field(min_length=1, max_length=200)
    district: str = Field(min_length=1, max_length=200)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    @field_validator("location_name", "district")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Location fields must not be blank")
        return value


class StoredRequest(AnalyzeResponse):
    request_id: str = Field(min_length=1, max_length=100)
    original_text: str = Field(min_length=1, max_length=5000)
    language: SupportedLanguage
    district: str | None = Field(max_length=200)
    latitude: float | None = Field(ge=-90, le=90)
    longitude: float | None = Field(ge=-180, le=180)
    confidence: float | None = Field(ge=0, le=1)
    created_at: AwareDatetime

    @model_validator(mode="after")
    def require_complete_coordinates(self) -> Self:
        resolved = (self.district, self.latitude, self.longitude)
        if any(value is not None for value in resolved):
            if self.location_name is None or any(value is None for value in resolved):
                raise ValueError("Resolved location must include district and both coordinates")
        return self


class RequestFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Category | None = None
    district: str | None = Field(default=None, min_length=1, max_length=200)
    language: SupportedLanguage | None = None
    limit: int = Field(default=100, ge=1, le=1000)

    @field_validator("district")
    @classmethod
    def normalize_district(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("District must not be blank")
        return value