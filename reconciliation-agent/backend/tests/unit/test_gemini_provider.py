from __future__ import annotations

import httpx
import pytest

from core.agent.llm.base import LLMError
from core.agent.llm.gemini_provider import GeminiProvider


class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def test_requires_api_key():
    with pytest.raises(LLMError):
        GeminiProvider(api_key="", model="gemini-3.6-flash")


def test_generate_extracts_text_from_valid_response(monkeypatch):
    provider = GeminiProvider(api_key="k", model="gemini-3.6-flash")
    ok = _FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": "Investigate the timing gap."}]}}]})
    monkeypatch.setattr(httpx, "post", lambda *a, **k: ok)
    assert provider.generate(system_prompt="sys", user_prompt="user") == "Investigate the timing gap."


def test_generate_captures_real_token_usage(monkeypatch):
    provider = GeminiProvider(api_key="k", model="gemini-3.6-flash")
    assert provider.last_usage is None
    response = _FakeResponse(200, {
        "candidates": [{"content": {"parts": [{"text": "OK"}]}}],
        "usageMetadata": {"promptTokenCount": 42, "candidatesTokenCount": 7, "thoughtsTokenCount": 15, "totalTokenCount": 64},
    })
    monkeypatch.setattr(httpx, "post", lambda *a, **k: response)
    provider.generate(system_prompt="sys", user_prompt="user")
    assert provider.last_usage.input_tokens == 42
    assert provider.last_usage.output_tokens == 7
    assert provider.last_usage.thoughts_tokens == 15
    assert provider.last_usage.total_tokens == 64


def test_generate_defaults_usage_to_zero_when_metadata_missing(monkeypatch):
    provider = GeminiProvider(api_key="k", model="gemini-3.6-flash")
    response = _FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": "OK"}]}}]})
    monkeypatch.setattr(httpx, "post", lambda *a, **k: response)
    provider.generate(system_prompt="sys", user_prompt="user")
    assert provider.last_usage.input_tokens == 0
    assert provider.last_usage.total_tokens == 0


def test_non_200_raises_llm_error(monkeypatch):
    provider = GeminiProvider(api_key="k", model="gemini-3.6-flash")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(429, text="rate limited"))
    with pytest.raises(LLMError):
        provider.generate(system_prompt="sys", user_prompt="user")


def test_empty_text_raises_llm_error(monkeypatch):
    provider = GeminiProvider(api_key="k", model="gemini-3.6-flash")
    empty = _FakeResponse(200, {"candidates": [{"content": {}, "finishReason": "MAX_TOKENS"}]})
    monkeypatch.setattr(httpx, "post", lambda *a, **k: empty)
    with pytest.raises(LLMError):
        provider.generate(system_prompt="sys", user_prompt="user")


def test_malformed_response_raises_llm_error(monkeypatch):
    provider = GeminiProvider(api_key="k", model="gemini-3.6-flash")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(200, {"unexpected": "shape"}))
    with pytest.raises(LLMError):
        provider.generate(system_prompt="sys", user_prompt="user")


def test_network_error_raises_llm_error(monkeypatch):
    provider = GeminiProvider(api_key="k", model="gemini-3.6-flash")

    def _raise(*a, **k):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(httpx, "post", _raise)
    with pytest.raises(LLMError):
        provider.generate(system_prompt="sys", user_prompt="user")
