"""
§27 — "Provider-neutral LLM adapter ... Model swap without logic change."

`LLMProvider` is the entire surface anything in this codebase is allowed
to know about an LLM vendor. Callers depend on this interface, never on a
concrete provider class, so swapping Gemini for Anthropic (or anything
else) later is a new class implementing this protocol, not a rewrite of
every call site.
"""
from __future__ import annotations

from typing import Protocol


class LLMError(Exception):
    """Any failure talking to a provider — timeout, HTTP error, malformed
    response, missing key. Callers treat every subclass the same way:
    §13.5's deterministic fallback, never a crashed agent run.
    """


class LLMProvider(Protocol):
    name: str
    model: str

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        """Returns the model's plain-text response, or raises LLMError."""
        ...
