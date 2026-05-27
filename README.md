# Memorycore

Memorycore is a durable memory layer for LLM and multi-agent systems. Its purpose is to give different models and tools access to the same structured memory store through a controlled interface, instead of relying only on chat history, hidden app memory, or one model's local context.

The basic idea is:

```text
LLM / agent / tool client
        ↓
MCP interface
        ↓
Memorycore service
        ↓
search + ranking + write candidates + audit
        ↓
structured memory store
```

## Core purpose

Memorycore is meant to store and retrieve useful long-term project memory:

- project facts
- decisions
- design notes
- source references
- summaries
- memory candidates
- audit records
- confidence and trust metadata
- later: embeddings, ranking scores, deduplication data, and experimental symbolic indexes

It should act as an external memory backbone that multiple LLMs can access through MCP or other APIs.

## MVP scope

The first version should stay small:

1. MCP server exposing memory tools.
2. Structured memory schema.
3. Search/read memory function.
4. Write-candidate workflow instead of uncontrolled direct writes.
5. Audit log for reads, proposed writes, accepted writes, rejected writes, and edits.
6. Project-scoped memory retrieval.

The MVP should not attempt to solve model training, autonomous self-replication, full agent orchestration, or symbolic glyph compression.

## Non-MVP experiments

Some ideas belong in experiments, not the core product:

- glyph memory compression
- swarm/blackboard memory coordination
- agent-lineage simulation memory
- Lisp + Mojo hybrid language concepts
- nano-LLM memory workers
- local model memory distillation

These can be documented and tested separately, but the canonical memory source should remain readable structured text plus raw evidence references.

## Design rule

Decentralize sensing and reasoning. Centralize state, memory, permissions, and audit.

Agents may search, summarize, classify, and propose memory updates. Memorycore should control the durable store, permissions, accepted writes, and audit trail.
