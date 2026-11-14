# Omni Memory Harness Results

The deterministic offline demo proves that an approved correction changes a
later agent run and records the outcome for future retrieval. It requires no
external account, API key, production data, or network access.

| Scenario | Correction available | Verification run | Outcome |
| --- | ---: | ---: | --- |
| Initial run | No | No | Failed |
| Corrected run | Yes | Yes | Passed |
| Correction reuse | 1 application | 1 success | 100% |

## Representative evidence run

Generated on 2026-07-19 from source revision
`68190cd670df8ecbd7dc309ff52704f688f0d839`. Identifiers are intentionally
unique for every run; the CI artifact contains the identifiers produced by the
submitted revision.

| Evidence | Value |
| --- | --- |
| Failed trajectory ID | `traj_7ca603420b3242a19b3669724e5210d5` |
| Correction ID | `corr_9fde76f858b34fb2996bf31fb533e969` |
| Successful trajectory ID | `traj_c025ac810a8642dca422cd349c82d79b` |
| Conflict-finding ID | `finding_bad475b29c8d48bb8363a00989149480` |
| Revision-decision ID | `revision_67cadc5d220e446db9a54e63d8d31114` |
| Repository revision | `68190cd670df8ecbd7dc309ff52704f688f0d839` |
| Demo duration | 0.0697 seconds |
| Projection file count | 14 |

## Reproduce it

```bash
./scripts/demo.sh --workspace ./demo-evidence
python scripts/verify_demo.py --report ./demo-evidence/demo-report.json
```

The structured result is written to `demo-evidence/demo-report.json`. The
hosted workflow also exports the full test output, OpenAPI schema, MCP tool
schemas, dependency metadata, commit and baseline state, wheel, source archive,
and generated synthetic Obsidian vault.

The offline provider remains the judge-safe default. Live GPT-5.6 evidence is
reported only after an authorized, sanitized request completes successfully;
an authentication success followed by model-access HTTP 403 is not represented
as a successful model execution.
