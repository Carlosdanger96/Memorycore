# Memorycore Design Decisions

## Product identity

Memorycore is a provider-neutral omni-memory system for general LLM use.

The core is not defined by Mistral, OpenAI, Anthropic, Google, Ollama, Hermes, Codex, a browser, an MCP host, or any other client. Those systems are consumers and producers of memory through adapters.

```text
Many LLMs, agents, applications, and workflows
                    ↓
             access adapters
                    ↓
              MemoryService
                    ↓
        canonical inspectable storage
```

## Canonical v0.1 architecture

```text
Application, script, or future integration
→ MemoryService
→ SQLite + FTS5
```

SQLite is the v0.1 source of truth. `MemoryService` owns validation and memory behavior.

The small v0.1 implementation is a foundation for omni-memory. It is not a statement that Memorycore is only a single-project note database.

## Provider neutrality

Provider and client identity may be recorded as provenance metadata, for example:

- `source_provider`;
- `source_model`;
- `source_client`;
- `source_session`;
- `source_uri`;
- `source_message_id`.

These fields describe origin. They must not force memories into provider-specific stores or provider-specific core APIs.

Provider SDKs, model calls, chat loops, and authentication belong in adapters or external applications, not in the storage core.

## Memory boundaries

The canonical memory layer should eventually support scopes such as user, workspace, project, session, topic, and visibility. Version 0.1 implements project scope first.

A provider name is not a primary scope. Different authorized LLMs should be able to retrieve the same memory when operating in the same allowed scope.

## Retrieval

FTS5 is implemented before vectors or embeddings. Retrieval is project-scoped, excludes archived memories, and ranks matching records using SQLite BM25 followed by recency.

Vectors, graphs, learned memory, rerankers, and consolidation may be added as optional derived capabilities. They must not replace readable canonical memory records.

## Durability

Normal memory lifecycle operations are add, update, archive, correct, and supersede. Permanent deletion should not become a casual public operation. Any future purge capability must be explicit, administrative, auditable, and separate from normal memory use.

Supersession must eventually link the old memory to its replacement. Changing only a status is insufficient because it loses the reason and replacement relationship.

## Integration layers

MCP is an optional future integration layer. It is not required to install, initialize, test, or use the v0.1 storage core.

The same rule applies to HTTP, browser, messaging, Signal, Obsidian, Hermes, Codex, Vibe, and other integrations: they expose or consume core behavior but do not redefine it.

## Main branch

Memorycore had no prior stable release, so the working v0.1 storage implementation becomes the canonical code on `main`. The former experimental code is preserved in `archive/pre-v0.1-experimental`.

Large experimental rewrites must not be merged into `main` merely because they contain more features. Changes should be small, tested, and compatible with the omni-memory architecture.

## Release meaning

`v0.1.0` means SQLite initialization, persistence, restart recovery, service CRUD/search/archive behavior, CLI health checks, tests, Windows validation, backup/restore documentation, and clean-install instructions have been verified.

MCP validation is not part of the v0.1 storage release gate.
