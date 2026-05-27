# Initial Memory Schema

This schema is intentionally simple. It defines readable memory records first. Embeddings, glyphs, model-generated indexes, and graph metadata can be attached later.

## Memory record

```json
{
  "id": "mem_001",
  "project": "memorycore",
  "source": "chat | file | github | manual | tool",
  "memory_type": "fact | decision | design | task | reference | warning | experiment",
  "summary": "Concise readable memory text.",
  "raw_evidence_ref": "Pointer to source text, file, commit, issue, or conversation.",
  "tags": ["mcp", "memory", "audit"],
  "trust_score": 0.8,
  "confidence": 0.9,
  "approval_status": "candidate | accepted | rejected | archived",
  "created_at": "2026-05-27T00:00:00Z",
  "updated_at": "2026-05-27T00:00:00Z",
  "created_by": "human | llm | tool",
  "audit_ref": "audit_001"
}
```

## Field notes

### `project`

Used to keep memories scoped. A query about Memorycore should not automatically pull unrelated cybersecurity, job-search, or drone-design memories unless explicitly requested.

### `source`

Tracks where the memory came from. This matters for trust, debugging, and later audit review.

### `memory_type`

Allows different retrieval behavior. A design decision should be weighted differently from a rough idea or unverified experiment.

### `summary`

Readable text remains the canonical memory representation.

### `raw_evidence_ref`

Memorycore should avoid unsupported memory claims. Each accepted memory should point back to evidence when possible.

### `trust_score`

A rough source-quality or acceptance score. This is not the same as relevance.

### `confidence`

How confident the system is that the memory is accurate and correctly summarized.

### `approval_status`

Durable memory should pass through a candidate stage before becoming accepted memory.

## Audit event

```json
{
  "id": "audit_001",
  "event_type": "read | candidate_created | accepted | rejected | edited | archived",
  "memory_id": "mem_001",
  "actor": "human | llm | tool",
  "timestamp": "2026-05-27T00:00:00Z",
  "reason": "Why this event happened.",
  "before": null,
  "after": "Optional changed content or metadata."
}
```

## Candidate write rule

LLMs and agents should create candidates. A policy layer, review step, or human approval should decide what becomes accepted durable memory.
