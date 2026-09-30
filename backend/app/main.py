import json
import logging
from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.dashboard import router as dashboard_router
from app.api.requests import router as requests_router
from app.api.hotspots import router as hotspots_router
from app.api.priorities import router as priorities_router
from app.api.recommendations import router as recommendations_router
from app.core.config import get_cors_origins

logger = logging.getLogger("uvicorn.error")


def create_app(cors_origins: list[str] | None = None) -> FastAPI:
    application = FastAPI(title="CivicPulse AI", version="0.8.0")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_origins() if cors_origins is None else cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Request-ID"],
    )

    @application.middleware("http")
    async def log_request(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = str(uuid4())
        request.state.request_id = request_id
        started_at = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            response = Response(status_code=500, content="Internal server error")
        response.headers["X-Request-ID"] = request_id
        logger.info(
            json.dumps(
                {
                    "request_id": request_id,
                    "operation": request.method,
                    "latency_ms": round((perf_counter() - started_at) * 1000, 2),
                    "status_code": response.status_code,
                    "success": response.status_code < 400,
                }
            )
        )
        return response

    application.include_router(health_router, prefix="/api/v1")
    application.include_router(dashboard_router, prefix="/api/v1")
    application.include_router(requests_router, prefix="/api/v1")
    application.include_router(hotspots_router, prefix="/api/v1")
    application.include_router(priorities_router, prefix="/api/v1")
    application.include_router(recommendations_router, prefix="/api/v1")
    return application


app = create_app()