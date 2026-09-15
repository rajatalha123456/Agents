"""Section 8.2 'architecture' CI job: the write-back guard, and an import
guard that fails if the pure statistics/selection core acquires a
database or HTTP dependency. This is what keeps sampling/statistics.py
and sampling/selection.py testable without any infrastructure.
"""
import ast
from pathlib import Path

import pytest

from sampling.api import assert_no_write_back_routes

SAMPLING_DIR = Path(__file__).resolve().parents[1] / "sampling"

FORBIDDEN_IMPORT_PREFIXES = ("sampling.db", "sampling.api", "sampling.api_v1", "sampling.auth", "sampling.jobs")

CORE_MODULES = ("statistics.py", "selection.py")


def test_no_write_back_routes():
    assert_no_write_back_routes()


def _imported_module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            prefix = "." * node.level
            names.add(prefix + node.module if node.level else node.module)
    return names


@pytest.mark.parametrize("filename", CORE_MODULES)
def test_core_module_has_no_infrastructure_dependency(filename):
    path = SAMPLING_DIR / filename
    imported = _imported_module_names(path)
    violations = [
        name for name in imported
        if any(name == prefix or name.startswith(prefix + ".") for prefix in FORBIDDEN_IMPORT_PREFIXES)
    ]
    assert not violations, (
        f"{filename} imports from {violations} -- statistics.py and selection.py "
        "must stay pure and testable without a database or HTTP framework."
    )
