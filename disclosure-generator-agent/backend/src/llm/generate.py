"""Orchestrates verify -> prompt -> generate -> numeric guard -> retry -> log.

Provider-specific code never appears here — only calls to
`src.llm.client.generate_text()`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src import config
from src.guard.numeric_guard import check_numeric_guard
from src.llm import client
from src.models.schemas import DisclosureStatus, Language, SignedRun, VerificationInfo
from src.signing.verify import VerificationResult, verify_signed_run
from src.storage.run_store import AuditRecord, append_record

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
GLOSSARY_PATH = Path(__file__).resolve().parent.parent / "glossary" / "glossary.json"

MAX_ATTEMPTS = 2


class GenerationUnavailableError(Exception):
    """The LLM backend could not be reached/responded invalidly.

    Distinct from a refusal: the request and payload were fine, but the
    service could not currently fulfill it. Callers (the API layer) should
    map this to a 503, not the 422 used for verification/numeric-guard
    refusals.
    """


@dataclass
class GenerationOutcome:
    run_id: str
    language: Language
    status: DisclosureStatus
    disclosure: str | None
    verification: VerificationInfo
    reason: str | None = None


def _load_system_prompt() -> str:
    return (PROMPTS_DIR / "system_prompt.txt").read_text(encoding="utf-8")


def _load_template(language: Language) -> str:
    return (PROMPTS_DIR / f"template_{language.value}.txt").read_text(encoding="utf-8")


def _load_glossary() -> dict:
    return json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))


def build_prompt(payload: dict, language: Language) -> tuple[str, str]:
    """Build the (system_prompt, user_prompt) pair for one language.

    Each language is generated independently from the same payload — this
    function is called separately per language, never chained off another
    language's output.
    """
    system_prompt = _load_system_prompt()
    template = _load_template(language)
    glossary = _load_glossary()

    user_prompt = template.format(
        payload_json=json.dumps(payload, indent=2, default=str, ensure_ascii=False),
        glossary_json=json.dumps(glossary, indent=2, ensure_ascii=False),
    )
    return system_prompt, user_prompt


def _verification_info(result: VerificationResult) -> VerificationInfo:
    return VerificationInfo(
        signature_valid=result.signature_valid,
        freshness_valid=result.freshness_valid,
        sanity_valid=result.sanity_valid,
    )


def _refuse(
    run_id: str,
    language: Language,
    verification_info: VerificationInfo,
    reason: str,
    verification_result_dict: dict,
    generated_output: str | None = None,
    numbers_used: list[str] | None = None,
) -> GenerationOutcome:
    append_record(
        AuditRecord.now(
            run_id=run_id,
            language=language.value,
            verification_result=verification_result_dict,
            generation_status="refused",
            generated_output=generated_output,
            numbers_used=numbers_used or [],
            failure_reason=reason,
        )
    )
    return GenerationOutcome(
        run_id=run_id,
        language=language,
        status=DisclosureStatus.REFUSED,
        disclosure=None,
        verification=verification_info,
        reason=reason,
    )


def generate_disclosure(signed_run: SignedRun, language: Language) -> GenerationOutcome:
    verification_result = verify_signed_run(signed_run)
    verification_info = _verification_info(verification_result)
    verification_dict = {
        "signature_valid": verification_result.signature_valid,
        "freshness_valid": verification_result.freshness_valid,
        "sanity_valid": verification_result.sanity_valid,
    }

    if not verification_result.valid:
        return _refuse(
            signed_run.run_id,
            language,
            verification_info,
            reason=f"verification failed: {verification_result.reason}",
            verification_result_dict=verification_dict,
        )

    payload_dict = signed_run.payload.model_dump(mode="json")
    system_prompt, user_prompt = build_prompt(payload_dict, language)

    last_text: str | None = None
    last_untraceable: list[str] = []

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            text = client.generate_text(system_prompt, user_prompt)
        except client.LLMError as exc:
            reason = f"generation unavailable: {exc}"
            append_record(
                AuditRecord.now(
                    run_id=signed_run.run_id,
                    language=language.value,
                    verification_result=verification_dict,
                    generation_status="refused",
                    generated_output=None,
                    numbers_used=[],
                    failure_reason=reason,
                )
            )
            raise GenerationUnavailableError(reason) from exc

        guard_result = check_numeric_guard(text, payload_dict)
        last_text = text
        last_untraceable = guard_result.untraceable_numbers

        if guard_result.passed:
            append_record(
                AuditRecord.now(
                    run_id=signed_run.run_id,
                    language=language.value,
                    verification_result=verification_dict,
                    generation_status="success",
                    generated_output=text,
                    numbers_used=[str(n) for n in sorted(guard_result.generated_numbers, key=str)],
                )
            )
            return GenerationOutcome(
                run_id=signed_run.run_id,
                language=language,
                status=DisclosureStatus.SUCCESS,
                disclosure=text,
                verification=verification_info,
            )

    return _refuse(
        signed_run.run_id,
        language,
        verification_info,
        reason=(
            "generated text contained untraceable numbers after "
            f"{MAX_ATTEMPTS} attempts: {last_untraceable}"
        ),
        verification_result_dict=verification_dict,
        generated_output=last_text,
        numbers_used=last_untraceable,
    )
