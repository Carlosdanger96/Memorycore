# Experience Correction Ledger

Memorycore stores reusable agent corrections as typed memories rather than free-form reflection. The first implementation is intentionally a correction ledger, not an autonomous graph-learning system.

## Record contract

An experience correction is a normal Memorycore record with:

- `memory_type: experience_correction`
- lifecycle status (`pending`, `active`, `rejected`, `archived`, or superseded states)
- normal provenance, client identity, confidence, audit history and project scope
- metadata schema `memorycore.experience_correction.v1`

Required correction fields:

- `task_type`
- `trigger`
- `failed_behavior`
- `operation`
- `instruction`

Optional scope fields:

- tools
- repositories
- applicability labels
- evidence

Supported operations are `add_step`, `remove_step`, `replace_step`, `reorder_steps`, `add_constraint`, `change_tool`, `narrow_scope`, `expand_search`, `require_verification`, and `escalate_approval`.

## Python example

```python
from memorycore import (
    CorrectionOperation,
    ExperienceCorrection,
    ExperienceCorrectionLedger,
    MemoryService,
)

service = MemoryService("data/memorycore.db")
ledger = ExperienceCorrectionLedger(service)

record = ledger.capture(
    project_id="omni-core",
    correction=ExperienceCorrection(
        task_type="obsidian_note_write",
        trigger="A requested note may already exist",
        failed_behavior="Created a duplicate after exact-title-only lookup",
        operation=CorrectionOperation.EXPAND_SEARCH.value,
        instruction="Search title, aliases, path and backlinks before creating a note",
        tools=("obsidian-rest",),
        repositories=("markdown-memory",),
    ),
    created_by="hermes",
    confidence=0.94,
    status="pending",
)
```

Approved corrections can be retrieved before a matching operation:

```python
corrections = ledger.retrieve(
    project_id="omni-core",
    task_type="obsidian_note_write",
    query="update canonical project note",
    tools=("obsidian-rest",),
    repositories=("markdown-memory",),
    minimum_confidence=0.75,
)
```

After use, record whether the correction transferred successfully:

```python
ledger.record_outcome(
    record.id,
    outcome="succeeded",
    updated_by="hermes",
    evidence="Canonical note updated without creating a duplicate",
)
```

## Runtime policy

1. Capture agent-generated corrections as `pending`.
2. Allow user-confirmed or test-confirmed corrections to become `active`.
3. Retrieve only active corrections before high-risk or repeated operations.
4. Inject only the instruction and minimal applicability context into the agent prompt.
5. Record reuse outcomes.
6. Supersede or archive corrections that fail repeatedly or become obsolete.
7. Do not generalize corrections across projects, tools or repositories without evidence.

## Obsidian Markdown mapping

Obsidian is an inspectable projection and review interface. Memorycore remains the canonical machine-readable source unless a future bidirectional synchronization protocol explicitly assigns authority.

Recommended vault structure:

```text
90_LLM_Exchange/
  Experience Corrections/
    Inbox/
    Active/
    Rejected/
    Archived/
    Indexes/
```

Each correction is one Markdown note named with its stable Memorycore ID:

```text
90_LLM_Exchange/Experience Corrections/Active/<memory-id>.md
```

Recommended frontmatter:

```yaml
---
schema: memorycore.experience_correction.v1
memory_id: 7aa72f5f-...
project: omni-core
memory_type: experience_correction
status: active
task_type: obsidian_note_write
operation: expand_search
confidence: 0.94
tools:
  - obsidian-rest
repositories:
  - markdown-memory
applicability:
  - create_note
  - update_note
created_by: hermes
source_type: system_event
created_at: 2026-07-16T22:00:00+00:00
updated_at: 2026-07-16T22:00:00+00:00
tags:
  - memory/experience-correction
  - operation/expand-search
  - project/omni-core
---
```

Recommended body:

```markdown
# Search before creating an Obsidian note

## Trigger
A requested project note may already exist.

## Failed behavior
The agent created a duplicate after checking only the exact title.

## Correction
Search title, aliases, path and backlinks before creating a note.

## Evidence
A retry updated the canonical note without creating another file.

## Reuse history
- Attempts: 1
- Successes: 1
- Failures: 0
- Last outcome: succeeded
```

## Obsidian responsibilities

Obsidian should provide:

- human review of pending corrections;
- backlinks to affected projects, tools and incident notes;
- dashboards grouped by task type, operation, status and confidence;
- conflict visibility when Markdown differs from the canonical Memorycore record;
- optional approval actions that call Memorycore rather than silently changing lifecycle state in a file.

Obsidian should not initially:

- infer corrections from arbitrary notes;
- directly mutate the SQLite database;
- automatically activate corrections because a Markdown file moved folders;
- merge corrections across projects without explicit review;
- treat backlinks as proof that a correction is valid.

## Synchronization phases

### Phase 1: One-way export

Memorycore exports active and pending correction records to Markdown. Obsidian is read/review oriented. This is the safest initial implementation.

### Phase 2: Approval commands

An Obsidian command or Omni Core action calls Memorycore MCP/REST to approve, reject, archive or supersede a correction, then refreshes the Markdown projection.

### Phase 3: Controlled bidirectional edits

Selected frontmatter/body fields may be edited in Obsidian. A sync adapter validates the schema, checks `updated_at` or a revision token, and submits a normal Memorycore update. Conflicts become review items rather than last-write-wins overwrites.

## Graph expansion later

Relationships can later be represented with normal memory links:

```text
correction -> derived_from -> failed trajectory
correction -> applies_to -> tool or task type
correction -> verified_by -> successful run or test
correction -> supersedes -> older correction
```

A dedicated graph database is not required for the first release. Add graph traversal only after correction-ledger retrieval has measurable limitations.
