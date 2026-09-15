"""
Core extraction agent — sends contract text to Gemini and forces
structured JSON output matching schemas.ContractAnalysis.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from schemas import ContractAnalysis

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH, override=False)


def get_api_key() -> str:
    raw_value = os.environ.get("GEMINI_API_KEY", "")
    cleaned = raw_value.strip().strip("`").strip().strip('"').strip("'")

    if not cleaned:
        raise RuntimeError(
            "GEMINI_API_KEY not set. Add it to your .env file as GEMINI_API_KEY=your-key-here"
        )

    os.environ["GEMINI_API_KEY"] = cleaned
    return cleaned

MODEL_NAME = "gemini-3.6-flash"  # use the currently supported Gemini model for new projects

SYSTEM_PROMPT = """You are a contract analysis agent for a financial/regulatory compliance context.
Read the contract text carefully and extract exactly the fields in the response schema.

Rules:
- Only report what is actually stated in the text. Never invent dates, amounts, or clauses.
- If a field genuinely isn't present in the contract, leave it empty/null rather than guessing.
- For "psr" (Payment Services Regulations / parties-scope-responsibilities): set applicable=true
  only if the contract references payment services, payment licensing, or a supervisory/regulatory
  body governing payments. Otherwise applicable=false.
- For conflicts: only flag genuine contradictions between two clauses (e.g. mismatched dates,
  contradictory termination terms, inconsistent liability caps). Do not flag stylistic differences.
- Set needs_human_review=true if the document is long/complex, has scanned/unreadable sections,
  or if you had low confidence on any major field. Explain why in review_notes.
- contract_type_confidence should reflect how clearly the document states or implies its type.
"""


def get_client() -> genai.Client:
    return genai.Client(api_key=get_api_key())


def analyze_contract(text: str, client: genai.Client = None) -> ContractAnalysis:
    """Send contract text to Gemini and get back a validated ContractAnalysis object."""
    client = client or get_client()

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[SYSTEM_PROMPT, "\n\n--- CONTRACT TEXT ---\n\n" + text],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ContractAnalysis,
            temperature=0.1,
        ),
    )

    return ContractAnalysis.model_validate_json(response.text)


def analyze_contract_chunks(chunks: list, client: genai.Client = None) -> ContractAnalysis:
    """
    For contracts split into multiple chunks: analyze each, then merge.
    """
    client = client or get_client()

    if len(chunks) == 1:
        return analyze_contract(chunks[0], client)

    results = [analyze_contract(chunk, client) for chunk in chunks]

    merged = results[0]
    for r in results[1:]:
        merged.fees.extend(r.fees)
        merged.loss_clauses.extend(r.loss_clauses)
        merged.dates.extend(r.dates)
        merged.conflicts.extend(r.conflicts)
        if r.needs_human_review:
            merged.needs_human_review = True
            merged.review_notes = f"{merged.review_notes or ''}\n{r.review_notes or ''}".strip()

    return merged