"""Opt-in inference-only tests: five billable calls per example, no storage."""

import asyncio
import os

import pytest
from app.agents.request_agent import RequestAgent
from app.core.config import get_gemini_settings
from app.services.gemini_service import GeminiService

pytestmark = [
    pytest.mark.gemini_live,
    pytest.mark.skipif(os.getenv("RUN_GEMINI_INTEGRATION") != "1", reason="Live Gemini validation is opt-in"),
]


def test_live_multilingual_analysis(citizen_example: tuple[str, str]) -> None:
    language, text = citizen_example
    result = asyncio.run(RequestAgent(GeminiService(get_gemini_settings())).analyze(text, request_id="live-inference"))
    assert result.language == language
    assert result.category == "Healthcare"
    assert result.location_name is None
    assert result.original_text == text
    assert "latitude" not in result.model_dump() and "longitude" not in result.model_dump()