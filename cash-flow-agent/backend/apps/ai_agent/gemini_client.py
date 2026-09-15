import json
import time

from django.conf import settings

SYSTEM_PROMPT = """You are a cash-flow and liquidity forecasting assistant embedded in a personal finance app.
You will be given a JSON snapshot of the user's financial data (current cash, assets, contributions,
withdrawals, payouts, a computed cash-flow forecast, and a liquidity score).

Rules:
- Only use the JSON data provided to you. Do not invent numbers.
- Never present your answer as a guaranteed financial outcome or as financial advice. Forecasts are
  estimates based on assumptions and may not reflect actual future results.
- Be concise and specific: reference actual months, amounts, and figures from the data.
- If the user asks in Roman Urdu or a mix of Urdu/English, reply in the same style. Otherwise reply in English.
"""


REQUEST_TIMEOUT_MS = 45_000


def _get_client():
    from google import genai
    from google.genai import types

    if not settings.GEMINI_API_KEY:
        return None
    return genai.Client(
        api_key=settings.GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
    )


def ask_gemini(question: str, context: dict) -> str:
    client = _get_client()
    if client is None:
        return (
            "AI chat is not configured yet — ask the administrator to set GEMINI_API_KEY "
            "in the backend .env file."
        )

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Financial data snapshot (JSON):\n{json.dumps(context, default=str)}\n\n"
        f"User question: {question}"
    )
    import httpx
    from google.genai import errors, types

    try:
        config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
        )
    except Exception:
        config = None

    transient_errors = (errors.ServerError, httpx.TimeoutException, httpx.ConnectError)

    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=config,
            )
            return response.text
        except transient_errors:
            if attempt == attempts:
                return (
                    "The AI service is currently overloaded and didn't respond in time. "
                    "Please try asking again in a moment."
                )
            time.sleep(2 * attempt)
        except Exception as exc:
            return f"AI chat request failed: {exc}"
