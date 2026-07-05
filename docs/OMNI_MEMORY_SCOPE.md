# Memorycore Omni-Memory Scope

## Mission

Memorycore provides one durable, inspectable memory substrate that multiple authorized LLMs, agents, applications, and workflows can share.

One client should be able to write a memory and another authorized client should be able to retrieve it without requiring the same model provider, SDK, chat interface, or agent framework.

## Core architecture

```text
LLMs / agents / applications / workflows
                 ↓
       provider-neutral adapters
                 ↓
            MemoryService
                 ↓
     canonical memory records
                 ↓
      storage and derived indexes
```

Canonical records are the source of truth. Search indexes, vectors, graphs, summaries, and learned representations are derived aids.

## Core responsibilities

Memorycore owns the canonical schema, validation, lifecycle behavior, provenance, scopes, retrieval contracts, migrations, import/export, auditability, integrity, backup, and recovery.

## Adapter responsibilities

Adapters translate client requests into Memorycore operations, attach source provenance, format retrieved context, and expose transport interfaces such as MCP, HTTP, CLI, browser, messaging, or native applications.

Adapters do not define a separate canonical database for each provider, make a provider object model the canonical schema, or replace readable records with derived representations.

## Memory organization

Memory should be organized by semantic and security boundaries rather than model vendor. Planned boundaries include user, workspace, project, session, topic, visibility, and permissions.

Provider and model names are provenance attributes. They describe where a memory came from; they do not identify an isolated provider-owned memory store.

## Canonical memory characteristics

A canonical memory should be readable without a model, addressable by a stable identifier, attributable when possible, scoped, timestamped, exportable, recoverable after restart, correctable without destroying history, and distinguishable from derived summaries and indexes.

## Outside the storage core

Provider chat clients, chat loops, model routing, application interfaces, agent orchestration, browser automation, messaging bots, and provider-specific authentication belong in separate integrations or applications built on Memorycore.

## Change review checklist

Before merging a change, verify:

1. It strengthens shared memory rather than building an unrelated application.
2. The core remains provider-neutral.
3. It preserves one canonical, readable source of truth.
4. Provider details remain provenance or adapter configuration.
5. New behavior stays behind a stable service boundary.
6. Failures remain distinguishable from not-found and no-results outcomes.
7. History is preserved through archive, correction, or linked supersession.
8. Schema changes include migrations and tests.
9. Experimental dependencies remain optional.
10. Documentation distinguishes stable, optional, experimental, and deferred behavior.

Changes that fail these checks should be revised, moved into an adapter, or kept experimental.
