# Three-Minute Omni Memory Harness Demo

## 0:00–0:20 — Problem

“Agents usually remember facts but forget how their behavior is implemented,
which execution failed, and which verified correction should be applied before
they try again. Omni Memory Harness adds that governed experience layer to
Memorycore.”

Run:

```bash
./scripts/demo.sh
```

## 0:20–0:45 — Behavior map

Open `Behaviors/agent.output.verify.md`. Show the exact synthetic source symbol,
line evidence, repository revision, related test, and confidence. State that the
scanner parsed text and AST only; it never executed repository code.

## 0:45–1:20 — Failed trajectory

Open the failed trajectory linked from `Dashboard.md`. Show `task_started`,
`tool_called`, `tool_result`, and `task_failed`. Point to the deterministic error
signature and the `agent.output.verify` behavior reference.

## 1:20–1:50 — Correction and successful rerun

Open the active `require_verification` correction. Show its failed-trajectory
evidence, immutable proposal/approval/application/outcome events, and **1/1
successful reuse** metric. Open the successful trajectory and show that the
context pack retrieved the correction before execution, followed by
`correction_applied`, `verification_run`, and `task_completed`.

## 1:50–2:20 — Conflict and governed revision

Open the contradiction finding. Show the two original memory IDs, explanation,
proposed replacement, model and prompt version, and approval decision. State
that the originals still exist as retired records and the LLM never performed a
silent rewrite.

## 2:20–2:40 — Obsidian and provenance

Return to `Dashboard.md`. Show counts, links, stable frontmatter, and the notice
that Markdown edits do not mutate canonical Memorycore data. Point to the
correction reuse success ratio, then open the projection
manifest and approval decision.

## 2:40–2:55 — Codex and GPT-5.6

“Codex implemented and verified the vertical slice from the recorded baseline.
The offline demo uses deterministic providers. With an authorized Platform
project, GPT-5.6 supplies strict structured correction and audit proposals;
Memorycore validates and approval-gates them.”

## 2:55–3:00 — Close

“The first run failed. The system converted that failure into governed reusable
experience, retrieved it before the second run, and proved the corrected run.”
