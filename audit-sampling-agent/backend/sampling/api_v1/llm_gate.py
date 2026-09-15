"""LLM enablement/residency gating (section 6.3).

If tenant.llm_enabled is false: 409, never a silent skip. If
data_residency_region is not 'default': the configured provider must have
an endpoint in that region, or 409 -- never a fallback to a global
endpoint. Provider choice is a deployment decision (LLMClient is
injected); no live provider is wired up in this environment, so a
deterministic stub stands in behind the same interface -- gating logic
below is provider-agnostic and unaffected by that.
"""
from __future__ import annotations

from fastapi import HTTPException

from ..db.models import Tenant
from ..llm import LLMClient

# Providers with a confirmed endpoint outside the default region. A real
# deployment would source this from provider configuration, not a
# hardcoded set; this is a placeholder for that lookup.
PROVIDER_REGIONS: dict[str, set[str]] = {
    "default_provider": {"default"},
}


def require_llm_enabled(tenant: Tenant) -> None:
    if not tenant.llm_enabled:
        raise HTTPException(
            status_code=409,
            detail=f"LLM features are disabled for tenant '{tenant.slug}'. "
            "An admin must enable llm_enabled and configure a provider before "
            "schema suggestions or narration are available.",
        )

    region = tenant.data_residency_region
    if region != "default":
        provider = tenant.llm_provider or ""
        allowed_regions = PROVIDER_REGIONS.get(provider, set())
        if region not in allowed_regions:
            raise HTTPException(
                status_code=409,
                detail=f"configured LLM provider '{provider}' has no confirmed endpoint in "
                f"residency region '{region}'; refusing to fall back to a global endpoint.",
            )


class DummyLLMClient(LLMClient):
    """Deterministic stand-in behind the LLMClient protocol. No live
    provider is configured in this environment; swapping this for a real
    client (OpenAI, Anthropic, an on-prem model, ...) is the only change
    needed to go live, since callers only depend on the LLMClient protocol.
    """

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> str:
        return "No live LLM provider is configured; this is a stub response."
