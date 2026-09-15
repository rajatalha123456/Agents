"""
Concrete `LLMProvider` for Google Gemini, talking to the REST
`generateContent` endpoint directly (no vendor SDK dependency — one
`httpx` call is the entire integration surface, matching how thin every
other provider adapter in this codebase is meant to be, §27).

This model generates an internal "thinking" pass before its visible
answer and spends output-token budget on it (confirmed by hand against
the live API — a 50-token budget was fully consumed by thinking with no
visible text returned), so `max_output_tokens` must leave headroom beyond
the visible narrative length actually wanted.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from core.agent.llm.base import LLMError

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


@dataclass(frozen=True)
class TokenUsage:
    """§21.5/§24 "cost per case" — real numbers from the provider's own
    `usageMetadata`, never estimated. `thoughts_tokens` is broken out
    separately because this model spends real output-token budget on an
    internal reasoning pass before its visible answer (§27's own note on
    `max_output_tokens`) — folding it into `output_tokens` would silently
    inflate what looks like "narrative" cost.
    """

    input_tokens: int
    output_tokens: int
    thoughts_tokens: int
    total_tokens: int


class GeminiProvider:
    name = "gemini"

    def __init__(self, *, api_key: str, model: str, timeout_seconds: float = 20.0, max_output_tokens: int = 1024):
        if not api_key:
            raise LLMError("Gemini provider requires an api_key")
        self._api_key = api_key
        self.model = model
        self._timeout = timeout_seconds
        self._max_output_tokens = max_output_tokens
        self.last_usage: TokenUsage | None = None  # set by the most recent generate() call

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        url = _ENDPOINT.format(model=self.model)
        body = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_prompt}]}],
            "generationConfig": {"maxOutputTokens": self._max_output_tokens, "temperature": 0.2},
        }
        try:
            response = httpx.post(url, params={"key": self._api_key}, json=body, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise LLMError(f"Gemini request failed: {exc}") from exc

        if response.status_code != 200:
            raise LLMError(f"Gemini returned HTTP {response.status_code}: {response.text[:300]}")

        try:
            data = response.json()
            candidates = data["candidates"]
            parts = candidates[0]["content"].get("parts", [])
            text = "".join(p.get("text", "") for p in parts).strip()
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"Gemini returned an unparseable response: {exc}") from exc

        if not text:
            finish_reason = data.get("candidates", [{}])[0].get("finishReason", "unknown")
            raise LLMError(f"Gemini returned no text (finishReason={finish_reason})")

        usage = data.get("usageMetadata", {})
        self.last_usage = TokenUsage(
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            thoughts_tokens=usage.get("thoughtsTokenCount", 0),
            total_tokens=usage.get("totalTokenCount", 0),
        )
        return text
