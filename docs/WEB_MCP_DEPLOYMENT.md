# Web MCP Deployment

Memorycore and SQLite can remain local. ChatGPT web should use OpenAI Secure MCP
Tunnel, which connects outbound from the local PC and does not make Memorycore
public. See [OpenAI Secure MCP Tunnel](OPENAI_SECURE_MCP_TUNNEL.md).

Mistral web currently uses a server URL connector. If no Mistral-managed private
tunnel is available for the account, that connector still needs a protected
public HTTPS bridge. The database remains private in either design.

## Security model

Each web connector gets a unique bearer token. The server maps that token to
its fixed client identity, role, model provenance, and project allowlist.
Tool arguments cannot override those values. Revoke a connector by deleting its
record and restarting the service.

Never commit the registry, share a token between connectors, publish SQLite,
or run HTTP with `MEMORYCORE_ALLOW_INSECURE_HTTP=true` outside a disposable
local test.

## Configure client identities

Copy `examples/http-clients.json.example` to a private location such as
`C:\Memorycore\secrets\http-clients.json`. Generate a distinct secret for each
`token` value:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Use `writer` for a connector that may propose memories and `approver` only for
a connector you explicitly trust to approve, correct, supersede, or archive.
Use a project allowlist for every client. The example assigns ChatGPT a writer
role and Mistral an approver role; change that deliberately for your workflow.

## Start the protected MCP service for a public URL connector

Set the service configuration on the machine that owns the database:

```powershell
$env:MEMORYCORE_DB = "C:\Memorycore\data\memorycore.db"
$env:MEMORYCORE_HTTP_TOKENS_FILE = "C:\Memorycore\secrets\http-clients.json"
$env:MEMORYCORE_PUBLIC_URL = "https://memory.example.com/mcp"
memorycore serve-http --host 127.0.0.1 --port 8000
```

`MEMORYCORE_PUBLIC_URL` must be the final HTTPS URL supplied to the web
connector. Bind Memorycore to `127.0.0.1`; put an HTTPS reverse proxy, secure
tunnel, or hosted gateway in front of it. The proxy must forward the
`Authorization: Bearer …` header unchanged and must not provide direct access
to the SQLite files.

## Connect URL-based web applications

In each provider's custom MCP connector settings, enter:

```text
Server URL: https://memory.example.com/mcp
Authentication: Bearer token
Token: the unique token assigned to that connector
```

Create separate connector entries for ChatGPT and Mistral. Availability of
custom connectors depends on the provider account, plan, region, and workspace
administrator settings. Use the connector's built-in test/discovery flow, then
verify `memory_health`, a pending write, a separate-client approval, retrieval,
and audit history.

## Before relying on it

- Use a real DNS name and HTTPS certificate; do not use an unauthenticated
  temporary URL for durable memory.
- Restrict tunnel access and rotate a token immediately if it appears in a
  chat, log, screenshot, or repository.
- Back up SQLite before upgrades. For concurrent multi-host production use,
  migrate the service database to PostgreSQL after its parity tests are complete.
