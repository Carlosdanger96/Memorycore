from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_base_package_remains_dependency_free() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["dependencies"] == []
    assert "omni-memory" in project["description"].lower()


def test_readme_defines_shared_provider_neutral_memory() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "provider-neutral omni-memory" in readme
    assert "one canonical memory source" in readme
    assert "provider integrations are replaceable access layers" in readme


def test_scope_document_keeps_integrations_outside_the_core() -> None:
    scope = (ROOT / "docs" / "OMNI_MEMORY_SCOPE.md").read_text(encoding="utf-8").lower()
    assert "provider-neutral adapters" in scope
    assert "canonical records are the source of truth" in scope
    assert "outside the storage core" in scope
