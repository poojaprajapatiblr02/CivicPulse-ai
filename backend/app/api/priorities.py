import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.config import get_bigquery_settings
from app.schemas.priorities import PriorityRecord
from app.services.bigquery_service import BigQueryService, BigQueryServiceError
from app.services.priority_service import PriorityService

router = APIRouter()
logger = logging.getLogger("uvicorn.error")
UNAVAILABLE = "Priority data is unavailable. Check BigQuery configuration and access."


def get_priority_service() -> PriorityService:
    try:
        return PriorityService(BigQueryService(get_bigquery_settings()))
    except Exception as error:
        logger.warning("operation=priority_config success=false error_type=%s", type(error).__name__)
        raise HTTPException(status_code=503, detail=UNAVAILABLE) from None


def read_results(request: Request, service: PriorityService, *, ranked: bool, limit: int) -> list[PriorityRecord]:
    try:
        return service.list_results(ranked=ranked, limit=limit)
    except (BigQueryServiceError, ValueError) as error:
        logger.warning("request_id=%s operation=priority_read success=false error_type=%s", request.state.request_id, type(error).__name__)
        raise HTTPException(status_code=503, detail=UNAVAILABLE) from None


@router.get("/gaps", response_model=list[PriorityRecord], tags=["Development Priorities"])
def get_gaps(
    request: Request, limit: int = Query(default=1000, ge=1, le=1000),
    service: PriorityService = Depends(get_priority_service),
) -> list[PriorityRecord]:
    return read_results(request, service, ranked=False, limit=limit)


@router.get("/priorities", response_model=list[PriorityRecord], tags=["Development Priorities"])
def get_priorities(
    request: Request, limit: int = Query(default=1000, ge=1, le=1000),
    service: PriorityService = Depends(get_priority_service),
) -> list[PriorityRecord]:
    return read_results(request, service, ranked=True, limit=limit)