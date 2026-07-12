# Install and Operate Memorycore

## Local SQLite service

Requirements: Python 3.11+ and Git. SQLite is included with Python.

```powershell
git clone https://github.com/Carlosdanger96/Memorycore.git
cd Memorycore
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup-windows.ps1 -StartService
```

This creates `.venv`, installs MCP support, initializes `data\memorycore.db`,
and starts a localhost-only endpoint at `http://127.0.0.1:8000/mcp`.

## Commands

```text
memorycore init
memorycore doctor
memorycore serve
memorycore serve-http --host 127.0.0.1 --port 8000
memorycore backup backup\memorycore.db
memorycore export export\memorycore.jsonl
memorycore import export\memorycore.jsonl
```

Run `.\scripts\verify-windows.ps1` to recheck the installation and tests.

## PostgreSQL central-service development

```powershell
docker compose up -d postgres
.\.venv\Scripts\python.exe -m pip install -e ".[postgres,mcp]"
$url = "postgresql+psycopg://memorycore:change-me-before-sharing@127.0.0.1:5432/memorycore"
.\.venv\Scripts\memorycore.exe --database-url $url serve-http --host 127.0.0.1 --port 8000
```

PostgreSQL still needs live integration validation before production use.

## Safety boundary

Keep database files and database credentials private. LLM clients use MCP and
do not receive direct database access. Keep HTTP bound to localhost until
token-derived remote identity and authorization are implemented.
