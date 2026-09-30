from functools import lru_cache
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import get_bigquery_settings
from app.schemas.dashboard import DashboardSummary
from app.services.bigquery_service import BigQueryService, BigQueryServiceError

router = APIRouter()
logger = logging.getLogger("uvicorn.error")
UNAVAILABLE = "Dashboard data is unavailable. Check BigQuery configuration and access."


@lru_cache(maxsize=1)
def get_bigquery_service() -> BigQueryService:
    try:
        return BigQueryService(get_bigquery_settings())
    except Exception as error:
        logger.warning("operation=bigquery_connect success=false error_type=%s", type(error).__name__)
        raise HTTPException(status_code=503, detail=UNAVAILABLE) from None


@router.get("/dashboard/summary", response_model=DashboardSummary, tags=["Dashboard"])
def get_dashboard_summary(service: BigQueryService = Depends(get_bigquery_service)) -> DashboardSummary:
    try:
        return service.dashboard_summary()
    except BigQueryServiceError:
        raise HTTPException(status_code=503, detail=UNAVAILABLE) from None