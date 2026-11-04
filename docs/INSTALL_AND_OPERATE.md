# Install and Operate Memorycore

## Local SQLite service

Requirements: Python 3.11+ and Git. SQLite is included with Python.

```powershell
git clone https://github.com/Carlosdanger96/Memorycore.git
cd Memorycore
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup-windows.ps1
```

This creates `.venv`, installs MCP support, and initializes `data\memorycore.db`.
For web connector deployment, use `-StartService -TokenFile <private-file>
-PublicUrl <https-url>` after creating the registry described in [Web MCP
Deployment](WEB_MCP_DEPLOYMENT.md). Normal HTTP mode requires bearer tokens.

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
The setup and verification scripts also find `uv` in the usual Windows user
locations when `python` is not on `PATH`.

The central HTTP service exposes `GET /readyz` on loopback. It returns only a
readiness boolean. A second HTTP service targeting the same database on this
host fails at startup; the operating-system lock releases after a crash.

## SQLite recovery

`backup` uses SQLite's online backup API and is the preferred whole-database
recovery artifact. Restore it while Memorycore is stopped by opening the backup
as the service database, then run `doctor` and a scoped search before reconnecting
clients. Do not copy a live WAL database file by itself.

`export` writes a version 2 JSONL snapshot with records, every memory and
access audit event, relationships, counts, and a SHA-256 trailer. The file is replaced only after
the complete export is flushed. `import` verifies that trailer and restores the
snapshot atomically into an **empty** initialized Memorycore database. It rejects
older partial JSONL exports because those cannot restore complete history and
links. Keep an untouched backup before attempting a restore.

## PostgreSQL central-service development

```powershell
docker compose up -d postgres
.\.venv\Scripts\python.exe -m pip install -e ".[postgres,mcp]"
$url = "postgresql+psycopg://memorycore:change-me-before-sharing@127.0.0.1:5432/memorycore"
.\.venv\Scripts\memorycore.exe --database-url $url serve-http --host 127.0.0.1 --port 8000
```

The integration suite uses `MEMORYCORE_TEST_POSTGRES_URL` to create and remove
its own disposable database. It checks project scoping, lifecycle, history,
links, restart persistence, duplicate detection, concurrent writes, and JSONL
recovery. The
GitHub Actions workflow runs this suite against a temporary PostgreSQL service.
JSONL export/import works on both storage adapters; for a PostgreSQL deployment,
also retain database-native backups under the operator's recovery policy.

## Safety boundary

Keep database files and database credentials private. LLM clients use MCP and
do not receive direct database access. HTTP identity is token-derived; see
[Web MCP Deployment](WEB_MCP_DEPLOYMENT.md) before exposing an endpoint.
