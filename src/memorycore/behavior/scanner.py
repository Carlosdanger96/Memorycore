from __future__ import annotations

import ast
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
import re
import subprocess
from typing import Iterable

from ..omni_models import BehaviorRecord, SourceEntrypoint


_SKIP_DIRECTORIES = {
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "dist", "build",
    "coverage", ".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__",
}
_SECRET_PATTERNS = {
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*credentials*",
    "*secret*", "*token*", "*.db", "*.sqlite", "*.sqlite3",
}
_CONFIG_SUFFIXES = {".json", ".yaml", ".yml", ".toml"}
_KNOWN_BEHAVIORS = {
    "plan_task": "agent.task.plan",
    "select_tool": "agent.tool.select",
    "execute_tool": "agent.tool.execute",
    "verify_output": "agent.output.verify",
    "request_memory_write": "agent.memory.write_request",
    "terminate_loop": "agent.loop.terminate",
}


class ScanSecurityError(ValueError):
    pass


@dataclass(slots=True)
class _Finding:
    path: str
    symbol: str
    line: int
    end_line: int
    language: str
    dependencies: list[str]


@dataclass(slots=True)
class _IgnoreRule:
    base: str
    pattern: str
    negated: bool
    directory_only: bool
    anchored: bool

    def matches(self, relative: str) -> bool:
        if self.base:
            if relative != self.base and not relative.startswith(self.base + "/"):
                return False
            candidate = relative[len(self.base):].lstrip("/")
        else:
            candidate = relative
        if not candidate:
            return False
        pattern = self.pattern.lstrip("/")
        parts = candidate.split("/")
        if self.directory_only:
            prefixes = ["/".join(parts[:index]) for index in range(1, len(parts) + 1)]
            if "/" in pattern or self.anchored:
                return any(fnmatch(prefix, pattern) for prefix in prefixes)
            return any(fnmatch(part, pattern) for part in parts[:-1])
        if "/" in pattern or self.anchored:
            return fnmatch(candidate, pattern)
        return any(fnmatch(part, pattern) for part in parts)


class RepositoryScanner:
    """Deterministic, read-only scanner. It parses text and never imports target code."""

    def __init__(self, allowed_roots: Iterable[str | Path]) -> None:
        self.allowed_roots = tuple(Path(root).expanduser().resolve() for root in allowed_roots)
        if not self.allowed_roots:
            raise ValueError("at least one scanner root must be allowed")

    def scan(self, repository_path: str | Path, *, project_id: str,
             repository: str | None = None) -> list[BehaviorRecord]:
        root = Path(repository_path).expanduser().resolve()
        if not root.is_dir() or not any(root == allowed or root.is_relative_to(allowed) for allowed in self.allowed_roots):
            raise ScanSecurityError("repository path is outside the configured allowed roots")
        revision = self._git_revision(root)
        repo_name = repository or root.name
        findings: list[_Finding] = []
        config_files: list[str] = []
        test_files: dict[str, str] = {}
        for path in self._files(root):
            relative = path.relative_to(root).as_posix()
            if path.suffix == ".py":
                parsed = self._python_findings(path, relative)
                findings.extend(parsed)
                if self._is_test(relative):
                    test_files[relative] = path.read_text(encoding="utf-8", errors="replace")[:1_000_000]
            elif path.suffix in {".ts", ".tsx"}:
                findings.extend(self._typescript_findings(path, relative))
                if self._is_test(relative):
                    test_files[relative] = path.read_text(encoding="utf-8", errors="replace")[:1_000_000]
            elif path.suffix in _CONFIG_SUFFIXES or path.name.endswith(".env.example"):
                config_files.append(relative)
        records: list[BehaviorRecord] = []
        for item in findings:
            behavior_id = self._behavior_id(item.symbol)
            tests = sorted(path for path, text in test_files.items() if item.symbol in text)
            label = behavior_id.rsplit(".", 1)[-1].replace("_", " ")
            records.append(BehaviorRecord(
                behavior_id=behavior_id,
                project_id=project_id,
                name=label.capitalize(),
                description=f"Repository behavior implemented by {item.symbol}.",
                repository=repo_name,
                repository_path=str(root),
                source_revision=revision,
                language=item.language,
                entrypoints=[SourceEntrypoint(
                    path=item.path, symbol=item.symbol, start_line=item.line,
                    end_line=item.end_line,
                )],
                configuration_sources=sorted(config_files),
                tests=tests,
                dependencies=item.dependencies,
                confidence=1.0 if item.symbol in _KNOWN_BEHAVIORS else 0.72,
            ))
        return self._merge(records)

    def _files(self, root: Path) -> Iterable[Path]:
        ignore_rules = self._ignore_rules(root)
        for path in sorted(root.rglob("*")):
            relative_path = path.relative_to(root)
            if (not path.is_file() or path.is_symlink() or
                    any(part in _SKIP_DIRECTORIES for part in relative_path.parts)):
                continue
            try:
                if not path.resolve().is_relative_to(root):
                    continue
            except OSError:
                continue
            relative = relative_path.as_posix()
            ignored = False
            for rule in ignore_rules:
                if rule.matches(relative):
                    ignored = not rule.negated
            if ignored:
                continue
            if path.stat().st_size > 1_000_000 or self._is_secret(path.name):
                continue
            if path.suffix in {".py", ".ts", ".tsx"} or path.suffix in _CONFIG_SUFFIXES or path.name.endswith(".env.example"):
                yield path

    @staticmethod
    def _ignore_rules(root: Path) -> list[_IgnoreRule]:
        files = []
        for path in root.rglob(".gitignore"):
            relative = path.relative_to(root)
            if (path.is_file() and not path.is_symlink() and
                    not any(part in _SKIP_DIRECTORIES for part in relative.parts)):
                files.append(path)
        rules: list[_IgnoreRule] = []
        for path in sorted(files, key=lambda item: (len(item.relative_to(root).parts), item.as_posix())):
            base = path.parent.relative_to(root).as_posix()
            if base == ".":
                base = ""
            for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw.rstrip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith(r"\#"):
                    line = line[1:]
                negated = line.startswith("!")
                if negated:
                    line = line[1:]
                elif line.startswith(r"\!"):
                    line = line[1:]
                directory_only = line.endswith("/")
                anchored = line.startswith("/")
                pattern = line.strip("/")
                if pattern:
                    rules.append(_IgnoreRule(base, pattern, negated, directory_only, anchored))
        return rules

    @staticmethod
    def _python_findings(path: Path, relative: str) -> list[_Finding]:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=relative)
        except SyntaxError:
            return []
        imports = sorted({
            node.module.split(".")[0] for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        } | {
            alias.name.split(".")[0] for node in ast.walk(tree)
            if isinstance(node, ast.Import) for alias in node.names
        })
        return [
            _Finding(relative, node.name, node.lineno, getattr(node, "end_lineno", node.lineno), "python", imports)
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and not node.name.startswith("_")
        ]

    @staticmethod
    def _typescript_findings(path: Path, relative: str) -> list[_Finding]:
        text = path.read_text(encoding="utf-8", errors="replace")
        dependencies = sorted(set(re.findall(r"from\s+['\"]([^'\"]+)['\"]", text)))
        pattern = re.compile(r"(?m)^\s*(?:export\s+)?(?:async\s+)?(?:function|class)\s+([A-Za-z_$][\w$]*)")
        findings = []
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append(_Finding(relative, match.group(1), line, line, "typescript", dependencies))
        return findings

    @staticmethod
    def _git_revision(root: Path) -> str:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], check=False,
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unversioned"

    @staticmethod
    def _behavior_id(symbol: str) -> str:
        if symbol in _KNOWN_BEHAVIORS:
            return _KNOWN_BEHAVIORS[symbol]
        normalized = re.sub(r"(?<!^)(?=[A-Z])", "_", symbol).lower()
        normalized = re.sub(r"[^a-z0-9_]+", "_", normalized).strip("_")
        return f"repository.behavior.{normalized}"

    @staticmethod
    def _merge(records: list[BehaviorRecord]) -> list[BehaviorRecord]:
        merged: dict[str, BehaviorRecord] = {}
        for record in records:
            current = merged.get(record.behavior_id)
            if current is None:
                merged[record.behavior_id] = record
            else:
                current.entrypoints.extend(record.entrypoints)
                current.tests = sorted(set(current.tests + record.tests))
                current.dependencies = sorted(set(current.dependencies + record.dependencies))
                current.confidence = max(current.confidence, record.confidence)
        return sorted(merged.values(), key=lambda item: item.behavior_id)

    @staticmethod
    def _is_secret(name: str) -> bool:
        lower = name.lower()
        if lower in {".env.example", ".env.sample", ".env.template"}:
            return False
        return any(fnmatch(lower, pattern) for pattern in _SECRET_PATTERNS)

    @staticmethod
    def _is_test(relative: str) -> bool:
        name = Path(relative).name.lower()
        return "test" in Path(relative).parts or name.startswith("test_") or ".test." in name or ".spec." in name
