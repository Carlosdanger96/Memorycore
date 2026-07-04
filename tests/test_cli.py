import json

from memorycore.cli import main


def test_init_and_doctor_without_mcp(tmp_path, capsys):
    database = tmp_path / "memory.db"

    assert main(["--db", str(database), "init"]) == 0
    initialized = json.loads(capsys.readouterr().out)
    assert initialized["ok"] is True
    assert initialized["command"] == "init"

    assert main(["--db", str(database), "doctor"]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["ok"] is True
    assert checked["fts5"] is True
