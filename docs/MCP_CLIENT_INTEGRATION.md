# Local MCP Client Integration

The local prototype uses two separate stdio MCP server processes that point to
the same SQLite database. Each process has a server-assigned identity and role.

| Client | Role | Purpose |
| --- | --- | --- |
| Mistral Vibe | `writer` | Adds pending memories and updates its own pending records. |
| Hermes | `approver` | Reviews, approves, corrects, and supersedes project memory. |

Copy the Mistral configuration from
`examples/clients/mistral-vibe-memorycore.toml` and configure Hermes with
`examples/clients/hermes-memorycore.env`. Both must use the same
`MEMORYCORE_DB` path.

The automated `test_cross_client.py` test validates the same MCP protocol
workflow without requiring either desktop application to be installed:

1. Mistral writes a pending memory.
2. Hermes retrieves pending memory and approves it.
3. Hermes corrects it.
4. Mistral retrieves the replacement as active.
5. Both inspect history after restart.

Do not expose the HTTP service remotely using these environment identities.
Remote access requires token-derived client identity and authorization.
