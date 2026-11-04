"""Preflight must distinguish runtime selection, absent packages and broken SDKs."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


spec = importlib.util.spec_from_file_location(
    "hermes_preflight", Path(__file__).parents[1] / "scripts/check-hermes-runtime.py")
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


@pytest.fixture
def source(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.11,<3.15"\n'
        'dependencies = ["openai==2.54.0; python_version >= \'3.14\'"]\n')
    (tmp_path / ".python-version").write_text(f"{sys.version_info.major}.{sys.version_info.minor}\n")
    monkeypatch.setattr(preflight.importlib, "import_module", lambda name: SimpleNamespace(
        OpenAI=object, AsyncOpenAI=object, ClientSession=object, __file__="isolated/sdk.py"))
    monkeypatch.setattr(preflight.importlib.metadata, "version", lambda name: "test-version")
    return tmp_path


def test_preflight_success_does_not_claim_handoff(source):
    report = preflight.inspect_runtime(source)
    assert report["sdk_preflight_passed"]
    assert report["model_handoff_verified"] is False


def test_updater_compatible_python_is_not_runtime_compatible(source):
    (source / ".python-version").write_text("99.0")
    report = preflight.inspect_runtime(source)
    assert report["errors"] == ["checkout_runtime_mismatch"]
    assert report["imports"]["openai"]["status"] == "ok"


@pytest.mark.parametrize("missing", ["openai", "openai.types.chat", "some_transitive_dependency"])
def test_missing_package_or_submodule_is_identified(source, monkeypatch, missing):
    def fail(name):
        raise ModuleNotFoundError("secret must not appear", name=missing)
    monkeypatch.setattr(preflight.importlib, "import_module", fail)
    report = preflight.inspect_runtime(source)
    assert not report["sdk_preflight_passed"]
    assert report["imports"]["openai"]["missing_module"] == missing
    assert "secret must not appear" not in str(report)


def test_old_or_shadowed_sdk_without_required_symbols(source, monkeypatch):
    monkeypatch.setattr(preflight.importlib, "import_module", lambda name: SimpleNamespace())
    report = preflight.inspect_runtime(source)
    assert report["imports"]["openai"]["missing_symbols"] == ["OpenAI", "AsyncOpenAI"]
    assert not report["sdk_preflight_passed"]


def test_import_failure_does_not_expose_exception_message(source, monkeypatch):
    def fail(name):
        raise RuntimeError("secret must not appear")
    monkeypatch.setattr(preflight.importlib, "import_module", fail)
    report = preflight.inspect_runtime(source)
    assert report["imports"]["openai"]["status"] == "import_failed"
    assert "secret must not appear" not in str(report)
