"""
Test isolation from real external state: a developer's local `.env`
(`GEMINI_API_KEY`) must never make the automated suite silently start
making live network calls — that's slow, costs real money, and makes
tests non-deterministic. Every test gets a clean, LLM-disabled `Settings`
by default; a test that specifically wants to exercise a configured
provider passes its own fake key + mocks the HTTP call (see
tests/unit/test_gemini_provider.py, test_llm_narrative.py), it doesn't
rely on ambient environment state.
"""
from __future__ import annotations

import pytest

from core.config import get_settings


@pytest.fixture(autouse=True)
def _no_real_llm_calls_in_tests(monkeypatch):
    # A real OS environment variable outranks both the repo-root .env file
    # and pydantic-settings' own defaults, so setting it to "" (not just
    # deleting it — deleting leaves the .env file itself still readable as
    # a lower-priority source) is what actually disables the provider here.
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("RECON_LLM__API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
