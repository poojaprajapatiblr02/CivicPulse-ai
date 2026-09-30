import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.agents.request_agent import RequestAgent
from app.core.config import get_bigquery_settings, get_gemini_settings
from app.schemas.analysis import AnalyzeRequest
from app.schemas.requests import RequestFilters, StoredRequest
from app.services.bigquery_service import BigQueryService, BigQueryServiceError
from app.services.gemini_service import GeminiService, GeminiServiceError, UNAVAILABLE

router = APIRouter()
logger = logging.getLogger("uvicorn.error")
STORAGE_UNAVAILABLE = "Request storage is unavailable. Check BigQuery configuration and access."


def get_gemini_service(request: Request) -> GeminiService:
    try:
        return GeminiService(get_gemini_settings())
    except Exception as error:
        logger.warning(
            "request_id=%s operation=gemini_config success=false error_type=%s",
            request.state.request_id, type(error).__name__,
        )
        raise HTTPException(status_code=503, detail=UNAVAILABLE) from None


def get_request_agent(service: GeminiService = Depends(get_gemini_service)) -> RequestAgent:
    return RequestAgent(service)


def get_request_store() -> BigQueryService:
    try:
        return BigQueryService(get_bigquery_settings())
    except Exception as error:
        logger.warning("operation=request_storage_config success=false error_type=%s", type(error).__name__)
        raise HTTPException(status_code=503, detail=STORAGE_UNAVAILABLE) from None


def get_created_at() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/requests", response_model=StoredRequest, status_code=201, tags=["Citizen Requests"])
@router.post("/requests/analyze", response_model=StoredRequest, status_code=201, tags=["Citizen Requests"])
async def analyze_request(
    payload: AnalyzeRequest, request: Request, agent: RequestAgent = Depends(get_request_agent),
    store: BigQueryService = Depends(get_request_store), created_at: datetime = Depends(get_created_at),
) -> StoredRequest:
    try:
        analysis = await agent.analyze(payload.text, request_id=request.state.request_id)
        return await run_in_threadpool(
            store.store_request, analysis, request_id=request.state.request_id, created_at=created_at,
        )
    except GeminiServiceError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None
    except (BigQueryServiceError, ValidationError) as error:
        logger.warning("request_id=%s operation=request_store success=false error_type=%s", request.state.request_id, type(error).__name__)
        raise HTTPException(status_code=503, detail=STORAGE_UNAVAILABLE) from None


@router.get("/requests", response_model=list[StoredRequest], tags=["Citizen Requests"])
def list_requests(
    filters: Annotated[RequestFilters, Query()], request: Request,
    store: BigQueryService = Depends(get_request_store),
) -> list[StoredRequest]:
    try:
        return store.list_requests(**filters.model_dump())
    except (BigQueryServiceError, ValidationError) as error:
        logger.warning("request_id=%s operation=request_list success=false error_type=%s", request.state.request_id, type(error).__name__)
        raise HTTPException(status_code=503, detail=STORAGE_UNAVAILABLE) from None