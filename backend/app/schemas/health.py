from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["healthy"] = "healthy"
    service: Literal["civicpulse-backend"] = "civicpulse-backend"