"""Read-only client dependency preflight; run with the intended Hermes Python.

Does not import Hermes (its bootstrap can repair/sync an installation), read
credentials, contact providers, or open Memorycore. Exit 0 means SDK preflight
passed, not that a model-driven memory handoff has been verified.
"""
import argparse
import importlib
import importlib.metadata
import json
from pathlib import Path
import sys
import tomllib


def inspect_runtime(source):
    project = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version_file = source / ".python-version"
    expected = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else None
    actual = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    errors = []
    # Respect the checkout's runtime selection, not just requires-python: older
    # interpreters may be admitted solely to allow Hermes' updater to run.
    if expected and not (actual == expected or actual.startswith(expected + ".")):
        errors.append("checkout_runtime_mismatch")
    checks = {}
    for module, symbols in (("openai", ("OpenAI", "AsyncOpenAI")),
                            ("openai.types.chat", ()), ("mcp", ("ClientSession",))):
        try:
            loaded = importlib.import_module(module)
            missing = [name for name in symbols if not hasattr(loaded, name)]
            checks[module] = {"status": "missing_symbols" if missing else "ok",
                              "missing_symbols": missing, "origin": getattr(loaded, "__file__", None)}
        except ModuleNotFoundError as exc:
            # Never include exception text: a loader could put secrets there.
            checks[module] = {"status": "missing_module", "missing_module": exc.name}
        except Exception as exc:
            checks[module] = {"status": "import_failed", "exception_type": type(exc).__name__}
        if checks[module]["status"] != "ok":
            errors.append("sdk_import_failed:" + module)
    versions = {}
    for name in ("openai", "mcp"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return {"python": sys.executable, "python_version": actual, "prefix": sys.prefix,
            "base_prefix": sys.base_prefix, "checkout_runtime": expected,
            "requires_python": project.get("requires-python"),
            "openai_declarations": [item for item in project.get("dependencies", [])
                                    if item.lower().startswith("openai")],
            "versions": versions, "imports": checks, "errors": errors,
            "sdk_preflight_passed": not errors, "model_handoff_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-source", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = inspect_runtime(args.hermes_source.resolve())
    except (OSError, KeyError, ValueError) as exc:
        print(json.dumps({"error": "invalid_hermes_checkout", "exception_type": type(exc).__name__}))
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["sdk_preflight_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
