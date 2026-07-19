from pathlib import Path

import pytest

from memorycore.behavior import RepositoryScanner, ScanSecurityError


def test_scanner_maps_python_typescript_tests_and_config_without_secrets(tmp_path):
    repo = tmp_path / "agent"
    repo.mkdir()
    (repo / "agent.py").write_text(
        "import json\n\ndef verify_output(value):\n    return bool(value)\n", encoding="utf-8"
    )
    (repo / "tools.ts").write_text(
        "import x from 'safe-lib';\nexport function select_tool() { return x; }\n", encoding="utf-8"
    )
    (repo / "test_agent.py").write_text("verify_output({})\n", encoding="utf-8")
    (repo / "agent.toml").write_text("enabled=true\n", encoding="utf-8")
    (repo / ".env").write_text("API_KEY=must-not-appear\n", encoding="utf-8")
    records = RepositoryScanner([tmp_path]).scan(repo, project_id="p", repository="agent")
    by_id = {item.behavior_id: item for item in records}
    assert "agent.output.verify" in by_id
    assert "agent.tool.select" in by_id
    assert "test_agent.py" in by_id["agent.output.verify"].tests
    serialized = str([item.to_dict() for item in records])
    assert "must-not-appear" not in serialized and ".env" not in serialized


def test_scanner_rejects_paths_outside_allowlist(tmp_path):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir(); outside.mkdir()
    with pytest.raises(ScanSecurityError):
        RepositoryScanner([allowed]).scan(outside, project_id="p")
