# Central Service Architecture

Memorycore is a service, not a database file shared directly by arbitrary LLM
processes.

## Current pivot

One Memorycore process exposes Streamable HTTP MCP at `/mcp`. All clients use
the same MCP tool contract; policy, lifecycle, retrieval, audit, and writes
remain inside that process.

```text
LLM clients → MCP (Streamable HTTP) → Memorycore service → storage adapter
```

SQLite + WAL is retained only for local single-host development and the initial
prototype. PostgreSQL is the production adapter for multi-machine clients and
concurrent writes. No client should receive direct production database access.

## Deployment phases

1. Central HTTP service with the existing SQLite adapter, bound to localhost.
2. PostgreSQL storage adapter and migrations, with the service as sole owner.
3. HTTPS Streamable HTTP endpoint with OAuth-derived client identity and roles.

The MCP interface, memory schema, lifecycle, and audit contract must remain
stable across those storage adapters.
