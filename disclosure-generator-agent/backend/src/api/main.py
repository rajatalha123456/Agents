"""FastAPI entrypoint: POST /disclosures/generate, GET /health.

Refusals (verification failure, numeric guard failure) return HTTP 422 with
a clean, non-alarming body — never a stack trace. Infrastructure failures
(LLM backend unreachable) return HTTP 503. Unexpected errors return a
generic HTTP 500 with no internal detail.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src import config
from src.llm.generate import GenerationUnavailableError, generate_disclosure
from src.models.schemas import DisclosureRequest, DisclosureResponse, DisclosureStatus

logger = logging.getLogger("disclosure_generator")

app = FastAPI(
    title="Disclosure Generator",
    description=(
        "Turns a cryptographically signed calculation run into a "
        "human-readable, numerically verified financial disclosure."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

if config.ENABLE_DEV_TOOLS:
    from src.api.dev_tools import router as dev_router

    app.include_router(dev_router)
    logger.warning("Dev tools enabled (POST /dev/sign). Never enable this in production.")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/disclosures/generate", response_model=DisclosureResponse)
def generate(request: DisclosureRequest):
    try:
        outcome = generate_disclosure(request.signed_run, request.language)
    except GenerationUnavailableError:
        logger.warning("disclosure generation unavailable (LLM backend unreachable)")
        raise HTTPException(
            status_code=503,
            detail="The disclosure generation service is temporarily unavailable. Please try again shortly.",
        )
    except Exception:
        logger.exception("unexpected error during disclosure generation")
        raise HTTPException(
            status_code=500,
            detail="An internal error prevented disclosure generation.",
        )

    response = DisclosureResponse(
        run_id=outcome.run_id,
        language=outcome.language,
        status=outcome.status,
        disclosure=outcome.disclosure,
        verification=outcome.verification,
        reason=outcome.reason,
    )

    if outcome.status == DisclosureStatus.REFUSED:
        return JSONResponse(status_code=422, content=response.model_dump(mode="json"))

    return response
