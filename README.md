# memory.exe-core

## What it is
An MCP-accessible external memory core for multiple LLMs.

## Problem
LLMs have fragmented memory across vendors and sessions.

## Solution
A shared memory service with project-scoped retrieval, source tracking, ACLs, and audit logs.

## Core Features
- MCP memory tools
- Durable memory store
- Hybrid retrieval
- Source-grounded memory records
- Write-candidate workflow
- Audit log
- Model/client permissions
- Optional Obsidian mirror

## MVP Tools
- `memory.search`
- `memory.write_candidate`
- `memory.get_project_context`
- `memory.open_raw`
- `memory.audit`

## Architecture
MCP Gateway → Policy Layer → Memory Engine → Storage → Workers

## MVP Scope
Phase 1 focuses on a smallest defensible release:
- MCP server
- memory schema
- search
- write candidates
- append-only audit logging

## Roadmap
- Phase 1: local MCP server
- Phase 2: Postgres storage
- Phase 3: retrieval and audit hardening
- Phase 4: Obsidian sync
- Phase 5: compression workers
- Phase 6: cloud deployment

## Initial Issue Backlog
1. Define memory object schema
2. Implement basic MCP server
3. Add `memory.search` tool
4. Add `memory.write_candidate` tool
5. Add local SQLite or Postgres storage
6. Add append-only audit log
7. Add project-scoped retrieval
8. Add ACL/policy checks
9. Create sample memory dataset
10. Write architecture documentation
