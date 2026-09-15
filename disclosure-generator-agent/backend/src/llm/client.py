"""Gemini LLM client. Everything above this module calls only
`generate_text()` and never touches the Gemini request/response shape
directly — swapping models or request params is a change contained
entirely to this file.
"""
from __future__ import annotations

import requests

from src import config

_THINK_CLOSE_TAG = "</think>"


class LLMError(Exception):
    """Base class for LLM generation failures."""


class LLMUnavailableError(LLMError):
    """The configured LLM backend could not be reached or timed out."""


class LLMResponseError(LLMError):
    """The LLM backend returned a malformed or empty response."""


def _strip_reasoning(text: str) -> str:
    # Defensive: if a future model/response ever includes a reasoning
    # block, only the text after the LAST "</think>" is the actual answer.
    # If no such marker is present, the text is used as-is.
    idx = text.lower().rfind(_THINK_CLOSE_TAG)
    if idx != -1:
        text = text[idx + len(_THINK_CLOSE_TAG):]
    return text.strip()


def _generate_gemini(system_prompt: str, user_prompt: str, temperature: float) -> str:
    if not config.GEMINI_API_KEY:
        raise LLMUnavailableError("GEMINI_API_KEY is not configured")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{config.GEMINI_MODEL}:generateContent?key={config.GEMINI_API_KEY}"
    )
    body = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    try:
        response = requests.post(url, json=body, timeout=config.LLM_TIMEOUT_SECONDS)
    except requests.exceptions.RequestException as exc:
        raise LLMUnavailableError("could not reach Gemini API") from exc

    if response.status_code != 200:
        raise LLMUnavailableError(f"Gemini returned HTTP {response.status_code}")

    try:
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMResponseError("Gemini returned an unexpected response shape") from exc

    if not text or not text.strip():
        raise LLMResponseError("Gemini returned empty content")

    return _strip_reasoning(text)


def generate_text(system_prompt: str, user_prompt: str, temperature: float | None = None) -> str:
    """Generate narration text from a system prompt + user prompt.

    Raises LLMUnavailableError or LLMResponseError on failure. Never
    returns partial/garbage text silently.
    """
    temperature = temperature if temperature is not None else config.LLM_TEMPERATURE
    return _generate_gemini(system_prompt, user_prompt, temperature)
