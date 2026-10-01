# Local MCP Client Integration

The local prototype uses two separate stdio MCP server processes that point to
the same SQLite database. Each process has a server-assigned identity and role.

| Client | Role | Purpose |
| --- | --- | --- |
| Mistral Vibe | `writer` | Adds pending memories and updates its own pending records. |
| Hermes | `reader` | Retrieves current memory, sources, and history. |
| Automated reviewer | `approver` | Verifies supported candidates and promotes or supersedes them atomically. |

Copy the Mistral configuration from
`examples/clients/mistral-vibe-memorycore.toml` and configure Hermes with
`examples/clients/hermes-memorycore.yaml` (or its `.env` companion). All must use the same
`MEMORYCORE_DB` path.

The [shared-memory cycle](SHARED_MEMORY_CYCLE.md) describes automated review,
the trusted source format, a six-step process test, and the remaining desktop
acceptance run. The reviewer has its own configuration in
`examples/clients/automated-reviewer.env`.

The older `test_cross_client.py` test retains the manual-approval MCP protocol
workflow without requiring either desktop application to be installed:

1. Mistral writes a pending memory.
2. Hermes retrieves pending memory and approves it.
3. Hermes corrects it.
4. Mistral retrieves the replacement as active.
5. Both inspect history after restart.

Do not expose the HTTP service remotely using these environment identities.
Remote access requires token-derived client identity and authorization.
