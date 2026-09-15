"""Regression test over the synthetic golden fixture set (see
tests/fixtures/golden/README.md). Runs the real, configured Gemini backend --
skipped automatically if no API key is configured, so this never blocks the
core suite in an environment without one.

Run explicitly with: pytest tests/test_golden_regression.py -v
Run the full 20-fixture set with: GOLDEN_FULL_RUN=1 pytest tests/test_golden_regression.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src import config
from src.llm.generate import generate_disclosure
from src.models.schemas import DisclosureRequest, DisclosureStatus

GOLDEN_DIR = Path(__file__).resolve().parent / "fixtures" / "golden"


def _load_fixtures() -> list[Path]:
    files = sorted(GOLDEN_DIR.glob("golden_*.json"))
    if not os.environ.get("GOLDEN_FULL_RUN"):
        files = files[:5]  # keep the default suite fast; full set is opt-in
    return files


pytestmark = pytest.mark.skipif(
    not config.GEMINI_API_KEY,
    reason="GEMINI_API_KEY not configured; skipping live golden regression",
)


@pytest.mark.parametrize("fixture_path", _load_fixtures(), ids=lambda p: p.stem)
def test_golden_fixture_generates_and_passes_numeric_guard(fixture_path: Path):
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    request = DisclosureRequest.model_validate(data)

    outcome = generate_disclosure(request.signed_run, request.language)

    assert outcome.status == DisclosureStatus.SUCCESS, (
        f"{fixture_path.name} refused: {outcome.reason}"
    )
    assert outcome.disclosure
