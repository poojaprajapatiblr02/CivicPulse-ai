from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

from app.agents.recommendation_agent import RecommendationAgent
from app.api.requests import get_created_at, get_gemini_service
from app.core.config import get_bigquery_settings
from app.schemas.recommendations import GenerateRecommendation, StoredRecommendation
from app.services.bigquery_service import BigQueryService, BigQueryServiceError
from app.services.gemini_service import GeminiService, GeminiServiceError
from app.services.recommendation_service import RecommendationEvidenceError, RecommendationService

router = APIRouter()
logger = logging.getLogger("uvicorn.error")
UNAVAILABLE = "Recommendation storage is unavailable. Check BigQuery configuration and access."


def get_recommendation_service() -> RecommendationService:
    try:
        return RecommendationService(BigQueryService(get_bigquery_settings()))
    except Exception as error:
        logger.warning("operation=recommendation_config success=false error_type=%s", type(error).__name__)
        raise HTTPException(status_code=503, detail=UNAVAILABLE) from None


def get_recommendation_agent(service: GeminiService = Depends(get_gemini_service)) -> RecommendationAgent:
    return RecommendationAgent(service)


@contextmanager
def recommendation_operation(request: Request) -> Iterator[None]:
    try:
        yield
    except (GeminiServiceError, RecommendationEvidenceError) as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from None
    except (BigQueryServiceError, ValueError, KeyError, TypeError) as error:
        logger.warning("request_id=%s operation=recommendation_storage success=false error_type=%s", request.state.request_id, type(error).__name__)
        raise HTTPException(status_code=503, detail=UNAVAILABLE) from None


@router.post("/recommendations/generate", response_model=StoredRecommendation, status_code=201, tags=["Recommendations"])
async def generate_recommendation(
    payload: GenerateRecommendation, request: Request,
    service: RecommendationService = Depends(get_recommendation_service),
    agent: RecommendationAgent = Depends(get_recommendation_agent),
    created_at: datetime = Depends(get_created_at),
) -> StoredRecommendation:
    with recommendation_operation(request):
        snapshot = await run_in_threadpool(service.get_evidence, str(payload.hotspot_id))
        result = await agent.generate(snapshot, request_id=request.state.request_id)
        return await run_in_threadpool(
            service.save, result, snapshot, recommendation_id=request.state.request_id, created_at=created_at,
        )


@router.get("/recommendations", response_model=list[StoredRecommendation], tags=["Recommendations"])
def list_recommendations(
    request: Request, limit: int = Query(default=100, ge=1, le=1000),
    service: RecommendationService = Depends(get_recommendation_service),
) -> list[StoredRecommendation]:
    with recommendation_operation(request):
        return service.list_recommendations(limit=limit)


@router.get("/recommendations/{id}", response_model=StoredRecommendation, tags=["Recommendations"])
def get_recommendation(
    id: UUID, request: Request, service: RecommendationService = Depends(get_recommendation_service),
) -> StoredRecommendation:
    with recommendation_operation(request):
        result = service.get_recommendation(str(id))
    if result is None:
        raise HTTPException(status_code=404, detail="Recommendation not found.")
    return result