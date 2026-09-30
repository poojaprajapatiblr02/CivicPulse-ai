from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class DashboardSummary(BaseModel):
    total_requests: int = Field(ge=0)
    requests_by_category: dict[str, int]
    total_population: int = Field(ge=0)
    infrastructure_records: int = Field(ge=0)
    total_investment: Decimal = Field(ge=0)
    currency: Literal["INR"] = "INR"
    data_source: Literal["SYNTHETIC / DEMO DATA"] = "SYNTHETIC / DEMO DATA"