# Local MCP Client Integration

The legacy local prototype uses two separate stdio MCP server processes that
point to the same SQLite database. The central-service target is one HTTP MCP
process that owns the database; Vibe and Hermes connect with separate tokens.
The server assigns each client's identity and role.

| Client | Role | Purpose |
| --- | --- | --- |
| Mistral Vibe | `writer` | Adds pending memories and updates its own pending records. |
| Hermes | `approver` | Reviews, approves, corrects, and supersedes project memory. |

Append the current Vibe example from
`examples/clients/mistral-vibe-memorycore.toml` to an isolated Vibe configuration.
For Hermes, merge
`examples/clients/hermes-memorycore.yaml.example` into a private test config
and replace its placeholder with a distinct token from the private registry.
Both clients use the same URL and never open the
database file. Keep live Omni client settings unchanged until Memorycore's
release gates pass.

Before launching an isolated Hermes client, follow
[Hermes runtime preflight](HERMES_RUNTIME_PREFLIGHT.md). Its Python runtime and
SDK dependencies belong to the client environment; Memorycore's service setup
does not install them. A passing MCP discovery check does not prove the model
client can load its SDK or complete a tool-driven handoff.

The automated `test_cross_client.py` test validates the same MCP protocol
workflow without requiring either desktop application to be installed:

1. Mistral writes a pending memory.
2. Hermes retrieves pending memory and approves it.
3. Hermes corrects it.
4. Mistral retrieves the replacement as active.
5. Both inspect history after restart.

Do not expose the HTTP service remotely using these environment identities.
Remote access requires token-derived client identity and authorization.
