# Codex Collaboration Record

## Work performed with Codex

- Inspected Memorycore storage, service, MCP, authorization, lifecycle, tests, and packaging.
- Recorded the clean pre-hackathon test baseline.
- Implemented the Omni Memory Harness vertical slice.
- Added scanner safety rules, deterministic signatures, secret redaction, lifecycle controls, and approval gates.
- Built and repeatedly ran the unit, interface, persistence, and end-to-end tests.
- Created the synthetic demonstration and Obsidian projection.
- Created the OpenAI Platform key through the OpenAI Developers plugin without exposing it.
- Verified the current Responses API structured-output contract against official OpenAI documentation.
- Diagnosed the live-provider 403 as model access for the selected Platform project, not a code or credential-format failure.

## Human decisions

- Omni Memory Harness extends the existing Memorycore repository.
- Memorycore remains the canonical governed store.
- Obsidian Markdown remains a projection and review surface.
- The hackathon demo uses synthetic data and deterministic providers by default.
- Canonical revisions require an approver.
- GPT-5.6 remains the explicit live default; the implementation does not silently substitute another model.

## Alternatives rejected

- A second independent memory platform.
- Direct SQLite access from REST or MCP adapters.
- Markdown as canonical storage.
- A graph database, Redis, PostgreSQL migration, Kubernetes, or a new frontend framework for the vertical slice.
- Executing scanned repository code.
- Automatic LLM rewriting of canonical memories.
- Making Hermes, OpenClaw, or Mistral Search demo dependencies.

## GPT-5.6 responsibilities

When enabled and authorized, GPT-5.6 receives bounded, redacted records and
returns strict structured correction or audit proposals. Memorycore validates
referenced IDs and schemas, stores findings as `pending_review`, and requires a
separate approver action before canonical state changes.

## Codex feedback evidence

`/feedback` session ID: **REQUIRED — NOT YET PROVIDED**

Do not replace this placeholder with an invented identifier.
