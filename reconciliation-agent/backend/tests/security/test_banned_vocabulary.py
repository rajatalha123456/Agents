"""
§2.2 / §29.2 — banned-vocabulary lint. `core/` must never contain a domain
word: if writing core code requires a domain term, that means an extension
point is missing (build the extension point, don't write the word).

This scans source text, so it also catches the word inside comments,
docstrings, and string literals — not just identifiers.
"""
from __future__ import annotations

import re
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[2] / "core"

# Words that belong to a specific domain pack (Islamic finance / Mizan,
# insurance, ...) and must never appear in core/. Update this list only
# when a genuinely new domain pack is being planned for — never to silence
# a real violation.
BANNED_WORDS = {
    "pool",
    "mudarabah",
    "mudarib",
    "wakalah",
    "policy_premium",
    "claim",
    "shariah",
    "fatwa",
    "qard",
    "murabaha",
    "takaful",
    "charity_payable",
    "purification",
}

# Files that are allowed to reference pack examples in prose (e.g. this
# test file itself, and the manifest schema's docstrings which quote §5.1's
# Islamic-finance example purely to explain the *mechanism*). Kept to an
# explicit, reviewed allowlist rather than a blanket carve-out.
ALLOWLIST = set()


def _iter_core_python_files():
    for path in CORE_DIR.rglob("*.py"):
        if path.name == "__pycache__":
            continue
        yield path


def test_core_package_has_no_banned_domain_vocabulary():
    violations: list[str] = []
    word_pattern = re.compile(
        r"\b(" + "|".join(re.escape(w) for w in BANNED_WORDS) + r")\b", re.IGNORECASE
    )

    for path in _iter_core_python_files():
        rel = path.relative_to(CORE_DIR.parent)
        if str(rel) in ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in word_pattern.finditer(line):
                violations.append(f"{rel}:{lineno}: banned word {match.group(0)!r} — {line.strip()}")

    assert not violations, (
        "core/ must stay domain-agnostic (§2.2). Found banned vocabulary:\n"
        + "\n".join(violations)
    )
