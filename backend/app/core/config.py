import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class GeminiSettings(BaseModel):
    project_id: str = Field(pattern=r"^[a-z][a-z0-9-]{4,61}[a-z0-9]$")
    region: str = Field(pattern=r"^[a-z][a-z0-9-]{1,62}$")
    model: str = Field(pattern=r"^gemini-[a-z0-9][a-z0-9.-]{1,100}$")
    timeout_seconds: float = Field(default=30, gt=0, le=120)


def get_gemini_settings() -> GeminiSettings:
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    return GeminiSettings.model_validate({
        "project_id": os.getenv("GCP_PROJECT_ID", ""),
        "region": os.getenv("GCP_REGION", ""),
        "model": os.getenv("GEMINI_MODEL", ""),
        "timeout_seconds": os.getenv("GEMINI_TIMEOUT_SECONDS", "30"),
    })


class BigQuerySettings(BaseModel):
    project_id: str = Field(pattern=r"^[a-z][a-z0-9-]{4,61}[a-z0-9]$")
    dataset: str = Field(default="civicpulse", pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,1023}$")
    location: str = Field(default="asia-south1", pattern=r"^[A-Za-z0-9-]+$")
    maximum_bytes_billed: int = Field(default=100_000_000, gt=0)
    table_prefix: str = Field(default='', pattern=r'^(?:[A-Za-z_][A-Za-z0-9_]{0,63})?$')


def get_bigquery_settings() -> BigQuerySettings:
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    return BigQuerySettings.model_validate({
        "project_id": os.getenv("GCP_PROJECT_ID", ""),
        "dataset": os.getenv("BIGQUERY_DATASET", "civicpulse"),
        "location": os.getenv("BIGQUERY_LOCATION", "asia-south1"),
        "maximum_bytes_billed": os.getenv("BIGQUERY_MAX_BYTES_BILLED", "100000000"),
        "table_prefix": os.getenv("BIGQUERY_TABLE_PREFIX", ""),
    })


class HotspotSettings(BaseModel):
    request_threshold: int = Field(default=20, ge=0)


def get_hotspot_settings() -> HotspotSettings:
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    return HotspotSettings(request_threshold=os.getenv("HOTSPOT_REQUEST_THRESHOLD", "20"))


def get_cors_origins() -> list[str]:
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    origins = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    )
    return [origin.strip() for origin in origins.split(",") if origin.strip()]