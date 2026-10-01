# Hermes efficiency trial

Run these two trials after the live shared-memory cycle passes. They target
Hermes configuration and terminal output, so neither requires a new memory
database, proxy service, or context compiler.

## Lazy MCP startup

`examples/clients/hermes-memorycore.yaml` is a Windows stdio configuration
template with `lazy: true` and a proposed `idle_timeout_seconds: 300`. Replace
the absolute interpreter and database paths and merge the entry into the
existing Hermes configuration. The 300-second value is a trial setting, not
a measured optimum. Preserve a copy of the original configuration first.

The first live connection populates Hermes' tool-schema cache. A missing or
stale cache falls back to eager connection, so the first launch cannot measure
the steady-state saving. Lazy startup defers the process; cached tool schemas
can still be registered in context. It is not proof of fewer prompt tokens.

| Measurement | Baseline | Trial | Acceptance |
| --- | --- | --- | --- |
| Warm-cache launch | `lazy: false` | `lazy: true` | No Memorycore child before the first tool call |
| First retrieval | Same project/query | Same project/query | Same record, revision and source |
| Startup time and RAM | Five comparable launches | Five comparable launches | Record median and range; retain only if useful |
| Idle recovery | No recycling | Wait beyond 300 seconds, retrieve again | Child restarts; same record and no extra writes |
| Retrieval latency | Warm and first-call latency | Warm and first-call latency | Record the startup delay moved onto first use |

Rollback: set `lazy: false` and `idle_timeout_seconds: 0`, then restart Hermes.
The database is unaffected. Inspect the process list and Hermes status display
to distinguish a cached lazy server from a failed connection.

## RTK trial

RTK's upstream Hermes integration uses a Python plugin to ask `rtk rewrite`
whether to rewrite a terminal command. Its documented setup command is:

```powershell
rtk --version
rtk init --agent hermes
```

Record the RTK and Hermes versions actually installed. The installer writes
`~/.hermes/plugins/rtk-rewrite/` and enables it in `plugins.enabled`. Preserve the
existing configuration first, including other enabled plugins. These commands
are instructions for the Windows host; this repository change does not execute
them or claim an installation.

Use a disposable checkout at a fixed commit and one diagnostic fixture that
intentionally fails. Compare raw and RTK output for `git status`, `git diff`,
`git log`, a representative search, and a focused test run. Inspect `rtk rewrite`
first: unsupported and compound commands can be left unchanged.

Record command, exit code, elapsed time, raw output path, compressed output
path, and output size. Token counts require the same tokenizer; byte savings
alone are not token savings. Keep raw failing output so omitted diagnostics
remain inspectable. Preserve both the failing assertion and the location
needed to repair it.

Proposed acceptance: no changed command effect or exit status, no missing
decisive diagnostic, and at least 20% median output reduction across commands
that are actually rewritten. This is a trial threshold, not an expected gain.
Also run once with RTK unavailable to confirm the plugin's documented fallback
to the original command on this host. Do not include memory JSON, provenance
receipts or source manifests in the compression experiment.

Rollback: remove only `rtk-rewrite` from `plugins.enabled` (or restore the
preserved configuration), then restart Hermes and rerun the same failing
diagnostic. Leave other plugins untouched. Keep the evidence even if RTK is
not retained.

## Source references

Upstream configuration and integration documents inspected on 2026-10-01:

- [Hermes MCP configuration reference](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/reference/mcp-config-reference.md)
- [RTK Hermes adapter](https://github.com/rtk-ai/rtk/blob/develop/hooks/hermes/README.md)

No startup, RAM, latency or token-saving measurements have been made on the
Windows host by this change. The context compiler and failure-memory loop stay
after the live memory cycle and these trials in the implementation order.
