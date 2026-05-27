# Memorycore Architecture Notes

## 1. System role

Memorycore is the persistent memory layer for LLM workflows, MCP clients, local agents, research tools, and future multi-agent systems.

It is not a chatbot. It is not the model itself. It is the external memory service that models can query and propose updates to.

## 2. Basic architecture

```text
Clients
  - ChatGPT / Le Chat / local LLMs
  - MCP clients
  - Obsidian bridge
  - CLI tools
  - research agents

        ↓

MCP / API boundary
  - memory.search
  - memory.get_project_context
  - memory.write_candidate
  - memory.open_raw
  - memory.audit

        ↓

Memorycore service
  - validation
  - permissions
  - project scoping
  - ranking
  - deduplication
  - trust/confidence scoring
  - write review
  - audit logging

        ↓

Storage
  - structured memory records
  - raw evidence references
  - audit log
  - embeddings/vector index later
  - optional experimental indexes later
```

## 3. Core memory record fields

Initial useful fields:

- `id`
- `project`
- `source`
- `memory_type`
- `summary`
- `raw_evidence_ref`
- `tags`
- `trust_score`
- `confidence`
- `approval_status`
- `created_at`
- `updated_at`
- `created_by`
- `audit_ref`

Additional experimental fields can be added later, but should not replace readable memory text.

## 4. Write-candidate workflow

Agents should not freely write durable memory.

Preferred flow:

```text
agent observes useful information
        ↓
agent proposes memory candidate
        ↓
Memorycore validates schema
        ↓
review / policy / confidence check
        ↓
accept, reject, merge, or revise
        ↓
audit event is written
```

This prevents memory poisoning, accidental duplication, and uncontrolled agent drift.

## 5. Retrieval workflow

Basic retrieval flow:

```text
query + project scope
        ↓
candidate memory search
        ↓
ranking / filtering
        ↓
return concise relevant records
        ↓
client model uses records in answer
```

The first version can use keyword or SQLite search. Later versions can add embeddings, rerankers, graph links, and small/nano memory workers.

## 6. Boundary between core and experiments

Core Memorycore should stay simple and reliable.

Allowed in core MVP:

- structured memory schema
- search/read
- write candidates
- audit log
- project scoping
- basic ranking

Keep out of core MVP:

- glyph compression
- self-replicating or lineage-evolving agents
- swarm blackboard experiments
- model-internal KV/cache transfer
- full custom Lisp/Mojo runtime
- autonomous write authority

Experiments can live under `/experiments/` and later graduate only after validation.
