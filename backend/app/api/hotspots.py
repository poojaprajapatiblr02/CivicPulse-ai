from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.core.config import get_bigquery_settings, get_hotspot_settings
from app.schemas.hotspots import Hotspot
from app.services.bigquery_service import BigQueryService, BigQueryServiceError
from app.services.hotspot_service import HotspotService
from app.services.priority_service import PriorityService

router = APIRouter()
logger = logging.getLogger("uvicorn.error")
UNAVAILABLE = "Hotspot data is unavailable. Check BigQuery configuration and access."


def get_hotspot_service() -> HotspotService:
    try:
        settings = get_hotspot_settings()
        return HotspotService(BigQueryService(get_bigquery_settings()), settings)
    except Exception as error:
        logger.warning("operation=hotspot_config success=false error_type=%s", type(error).__name__)
        raise HTTPException(status_code=503, detail=UNAVAILABLE) from None


def get_detection_time() -> datetime:
    return datetime.now(timezone.utc)


@contextmanager
def hotspot_operation(request: Request, operation: str) -> Iterator[None]:
    try:
        yield
    except (BigQueryServiceError, ValueError) as error:
        logger.warning("request_id=%s operation=%s success=false error_type=%s", request.state.request_id, operation, type(error).__name__)
        raise HTTPException(status_code=503, detail=UNAVAILABLE) from None


@router.post("/hotspots/detect", response_model=list[Hotspot], tags=["Hotspots"])
def detect_hotspots(
    request: Request, service: HotspotService = Depends(get_hotspot_service),
    as_of: datetime = Depends(get_detection_time),
) -> list[Hotspot]:
    with hotspot_operation(request, "hotspot_detect"):
        hotspots = service.detect(as_of=as_of)
        PriorityService(service.store).refresh(hotspots)
        return hotspots


@router.get("/hotspots", response_model=list[Hotspot], tags=["Hotspots"])
def list_hotspots(
    request: Request, limit: int = Query(default=1000, ge=1, le=1000),
    service: HotspotService = Depends(get_hotspot_service),
) -> list[Hotspot]:
    with hotspot_operation(request, "hotspot_list"):
        return service.list_hotspots(limit=limit)


@router.get("/hotspots/{id}", response_model=Hotspot, tags=["Hotspots"])
def get_hotspot(
    id: UUID, request: Request, service: HotspotService = Depends(get_hotspot_service),
) -> Hotspot:
    with hotspot_operation(request, "hotspot_get"):
        hotspot = service.get_hotspot(str(id))
    if hotspot is None:
        raise HTTPException(status_code=404, detail="Hotspot not found.")
    return hotspot