from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.schemas.analysis import Category
from app.schemas.requests import ResolvedLocation


class Hotspot(ResolvedLocation):
    hotspot_id: str = Field(min_length=1, max_length=100)
    category: Category
    request_count: int = Field(gt=0)
    affected_population: int = Field(ge=0)
    average_urgency: float = Field(ge=0, le=1)
    demand_growth: float | None = Field(ge=-1)
    created_at: AwareDatetime


class HotspotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, frozen=True)
    request_id: str = Field(min_length=1, max_length=100)
    location_name: str | None = Field(max_length=200)
    district: str | None = Field(max_length=200)
    category: Category
    urgency: float = Field(ge=0, le=1)
    created_at: AwareDatetime


class HotspotLocation(ResolvedLocation):
    population: int = Field(ge=0)