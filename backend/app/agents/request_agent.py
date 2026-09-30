import asyncio
from collections.abc import Awaitable, Callable
import json
import logging
from time import perf_counter
from typing import Any

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context
from pydantic import ValidationError

from app.agents.understanding_agents import (
    ClassificationAgent, EntityExtractionAgent, LanguageDetectionAgent,
    LocationExtractionAgent, UrgencyAnalysisAgent,
)
from app.schemas.analysis import AnalyzeResponse
from app.schemas.request_agent import RequestAgentState
from app.services.gemini_service import GeminiService, GeminiServiceError, INVALID_OUTPUT, TIMEOUT, UNAVAILABLE

logger = logging.getLogger("uvicorn.error")
Node = Callable[[RequestAgentState], Awaitable[dict[str, Any]]]


def logged_node(name: str, operation: Node) -> Node:
    async def run(state: RequestAgentState) -> dict[str, Any]:
        started_at = perf_counter()
        success = False
        error_type: str | None = None
        try:
            update = await operation(state)
            RequestAgentState.model_validate({**state.model_dump(), **update})
            success = True
            return update
        except GeminiServiceError as error:
            error_type = f"AgentHTTP{error.status_code}"
            raise
        except ValidationError:
            error_type = "InvalidAgentState"
            raise GeminiServiceError(502, INVALID_OUTPUT) from None
        except asyncio.CancelledError:
            error_type = "Cancelled"
            raise
        except Exception as error:
            error_type = type(error).__name__
            raise GeminiServiceError(503, UNAVAILABLE) from None
        finally:
            logger.info(json.dumps({
                "request_id": state.request_id, "operation": "request_agent_node",
                "node": name, "latency_ms": round((perf_counter() - started_at) * 1000, 2),
                "success": success, "error_type": error_type,
            }))
    return run


async def validate_analysis(state: RequestAgentState) -> dict[str, AnalyzeResponse]:
    language = state.language_result
    classification = state.classification_result
    entities = state.entity_result
    location = state.location_result
    urgency = state.urgency_result
    if language is None or classification is None or entities is None or location is None or urgency is None:
        raise GeminiServiceError(502, INVALID_OUTPUT)
    place = location.location_name
    if place is not None and place.casefold() not in state.text.casefold():
        place = None
    response = AnalyzeResponse(
        original_text=state.text, language=language.language, category=classification.category,
        sub_category=classification.sub_category, problem=entities.problem,
        location_name=place, urgency=urgency.urgency,
        confidence=min(result.confidence for result in (language, classification, entities, location, urgency)),
    )
    return {"response": response}


class RequestAgent:
    def __init__(self, service: GeminiService) -> None:
        self.service = service
        agents = (
            LanguageDetectionAgent(service), ClassificationAgent(service),
            EntityExtractionAgent(service), LocationExtractionAgent(service), UrgencyAnalysisAgent(service),
        )
        graph = StateGraph(RequestAgentState)
        previous = START
        for agent in agents:
            graph.add_node(agent.name, logged_node(agent.name, agent.run))
            graph.add_edge(previous, agent.name)
            previous = agent.name
        graph.add_node("validation", logged_node("validation", validate_analysis))
        graph.add_edge(previous, "validation")
        graph.add_edge("validation", END)
        self.graph = graph.compile()

    async def analyze(self, text: str, *, request_id: str) -> AnalyzeResponse:
        state = RequestAgentState(text=text, request_id=request_id)
        try:
            with tracing_context(enabled=False, parent=False):
                async with asyncio.timeout(self.service.settings.timeout_seconds * 5 + 5):
                    output = await self.graph.ainvoke(state, config={"recursion_limit": 10, "callbacks": []})
            result = RequestAgentState.model_validate(output)
            if result.response is None:
                raise GeminiServiceError(502, INVALID_OUTPUT)
            return result.response
        except TimeoutError:
            raise GeminiServiceError(504, TIMEOUT) from None
        except GeminiServiceError:
            raise
        except ValidationError:
            raise GeminiServiceError(502, INVALID_OUTPUT) from None
        except Exception:
            raise GeminiServiceError(503, UNAVAILABLE) from None