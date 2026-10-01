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
memorycore check
memorycore serve
memorycore serve-http --host 127.0.0.1 --port 8000
memorycore --client <id> --role <role> add --project <project> --type <type> --content "<text>"
memorycore get <memory-id>
memorycore search "<query>" --project <project>
memorycore --client <id> --role <role> update <memory-id> --summary "<text>" --expected-revision <n>
memorycore --client <id> --role approver approve <memory-id>
memorycore --client <id> --role approver reject <memory-id>
memorycore --client <id> --role approver archive <memory-id>
memorycore history <memory-id>
memorycore projects
memorycore backup backup\memorycore.db
memorycore restore backup\memorycore.db
memorycore export export\memorycore.jsonl
memorycore import export\memorycore.jsonl
memorycore project <project> --vault <obsidian-vault>
```

Roles are `reader`, `writer`, `approver`, and `administrator`; writers create
pending records unless policy explicitly permits active creation. CLI and MCP
share the same policy contract, so lifecycle, permission, duplicate,
provenance, and revision rules are identical across both interfaces.

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
do not receive direct database access. HTTP identity is token-derived; see
[Web MCP Deployment](WEB_MCP_DEPLOYMENT.md) before exposing an endpoint.
