"""Thin wrapper so the rest of the app doesn't care which LLM backend is configured.

Switch via LLM_PROVIDER in .env:
  - "anthropic": hosted API, needs ANTHROPIC_API_KEY. Paid, but very reliable at
     following the strict JSON/grounding instructions.
  - "gemini": hosted API, needs GEMINI_API_KEY — free tier available via Google
     AI Studio (aistudio.google.com/apikey), no card required to start. Good
     option if you don't want to pay for the Anthropic API during dev/testing.
  - "ollama": fully local/on-prem model, completely free, no API key at all —
     use this if data-residency rules mean queries (which may include
     confidential internal policy text) cannot leave your network (see NFR-3
     and open question #3 in the requirements doc).
"""
from app.config import settings
from app.agent.prompts import SYSTEM_PROMPT


def generate(user_prompt: str) -> str:
    if settings.llm_provider == "anthropic":
        return _generate_anthropic(user_prompt)
    if settings.llm_provider == "gemini":
        return _generate_gemini(user_prompt)
    if settings.llm_provider == "ollama":
        return _generate_ollama(user_prompt)
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider}")


def _generate_anthropic(user_prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def _generate_gemini(user_prompt: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
        ),
    )
    return response.text


def _generate_ollama(user_prompt: str) -> str:
    import ollama

    client = ollama.Client(host=settings.ollama_host)
    response = client.chat(
        model=settings.ollama_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        format="json",
    )
    return response["message"]["content"]
