# Shared-memory cycle

This milestone extends the base shared-memory work in PR #12. SQLite remains
canonical. Obsidian remains a projection. The change adds a review operation
and a reproducible protocol test; it does not add an orchestration system.

## Six acceptance steps

| Step | Operation | Required evidence |
| --- | --- | --- |
| 1 | Hermes retrieves the current decision | Record ID, revision, source URI and source ID |
| 2 | Vibe submits a candidate | Writer identity; pending status; absent from normal retrieval |
| 3 | Automated reviewer evaluates it | Exact content hash, candidate revision, source snapshot hash, durable verdict |
| 4 | Hermes retrieves the promoted record | Same ID and source; active status |
| 5 | Vibe submits a sourced correction; reviewer promotes it | Original superseded, one link, correction alone in normal retrieval |
| 6 | All service processes exit and restart | Same correction, revision and source; repeated current submission and review add no records or events |

`tests/test_shared_cycle.py` runs these steps through real MCP stdio servers
and a separate CLI reviewer. It keeps Hermes and Vibe connected during the
initial exchange, closes every server, then launches fresh processes. A final
SQLite integrity check verifies three records, one supersession link and two
review receipts. The names Hermes and Vibe identify protocol clients in this
test; their desktop applications are not launched. Source decisions and the
database are synthetic and temporary.

Run from the branch containing this change:

```powershell
python -m pip install -e ".[mcp-test]"
$env:MEMORYCORE_CYCLE_REPORT = "$PWD\shared-cycle-report.json"
python -m pytest tests/test_shared_cycle.py tests/test_review.py -v
Remove-Item Env:MEMORYCORE_CYCLE_REPORT
```

CI runs the cycle on Linux Python 3.11–3.13, Windows, and the installed wheel.
Linux and Windows jobs retain the JSON evidence as workflow artifacts. An
incomplete run has `ok: false` and includes only steps actually completed.

## Automated review contract

The shared service method is `MemoryService.review_memory`. Both adapters call
that method, so CLI and MCP use the same policy, evidence and commit checks.

MCP arguments:

```json
{
  "memory_id": "candidate-id-from-memory_add",
  "expected_revision": 0,
  "expected_content_sha256": "sha256-of-the-returned-content-as-UTF-8"
}
```

The MCP tool is `memory_review`. The equivalent CLI call is:

```powershell
memorycore review <candidate-id> --expected-revision 0 --content-sha256 <sha256>
```

Set `MEMORYCORE_DB`, `MEMORYCORE_CLIENT_ID=automated-reviewer`,
`MEMORYCORE_CLIENT_ROLE=approver`, `MEMORYCORE_ALLOWED_PROJECTS`, and
`MEMORYCORE_REVIEW_SOURCES_FILE` in that process's environment first. The
reviewer must have a different identity from the writer. Readers, writers,
read-only policies and out-of-project reviewers cannot call this operation.

The source file is an operator-controlled export of trusted decisions. The
example in `examples/review/trusted-decisions.example.json` is a synthetic
fixture, not project evidence. A candidate cannot choose the file path or ask
the server to fetch a URL. Source URIs are provenance identifiers, not network
requests. The reviewer verifies the configured snapshot; it does not establish
whether the upstream document changed since that snapshot was prepared.

Each entry supplies `project_id`, `memory_type`, `content`, `source_type`,
`source_uri`, and `source_id`. Optional `summary`, `tags`, `metadata` and
`confidence` default to `null`, `[]`, `{}` and `null`. All of these fields must
match the candidate exactly, including punctuation. This also prevents an
unsupported summary or ranking metadata from hitching a ride on a valid quote.
The source identity tuple must be unique within the manifest. The entire
manifest is bounded to 1 MiB and its exact byte hash is retained in the receipt.

| Verdict | Meaning | State change |
| --- | --- | --- |
| `confirmed` | Exact record matches the trusted source decision | Pending → active |
| `rejected` | A known source decision differs from the submitted record | Pending → rejected |
| `needs_validation` | No matching trusted decision, or LLM inference | Remains pending |

This is deliberately an exact-decision reviewer. It cannot judge paraphrases,
discover contradictory evidence, validate arbitrary web claims, or perform
semantic sensitivity screening. The trusted decision export must already be
appropriate for promotion. Unknown or ambiguous evidence never auto-promotes.
Missing or malformed configuration is an error with no memory mutation.

## Correction and transaction guarantees

A correction is a new pending candidate with its own source identity. Its
trusted source entry additionally contains:

```json
{
  "supersedes": {
    "memory_id": "currently-active-record-id",
    "revision": 1
  }
}
```

Only the source manifest authorizes that link. Candidate metadata cannot
silently select a record to retire. The original must still be active, at the
specified revision, and in the same project and memory type. Retire the old
source entry from the trusted manifest when publishing its correction.

The database rechecks the complete candidate snapshot under `BEGIN IMMEDIATE`.
Promotion, original retirement, the link, lifecycle audit events and the review
receipt commit together. A concurrent edit, stale target revision or write
failure rolls back the entire transition. The original and the correction
retain their own sources and writer attribution.

Repeated review of the same candidate revision, content hash, source snapshot
hash and reviewer identity returns the durable receipt without another write.
`replayed: true` describes a historical review; the returned `memory` is the
current record. A changed manifest creates a different review request.
Normal reads filter to active records. Explicit ID/history reads still expose
superseded records for inspection.

Submission deduplication retains the base layer's **live-record** semantics.
This milestone proves retries of the current correction after restart. It does
not introduce a permanent submission-request ledger: resubmitting retired
content can create a new pending record. Removing retired decisions from the
trusted manifest prevents that stale source from being automatically promoted.

## Trust and live acceptance

Local stdio identities and CLI roles are configuration, not an OS security
boundary against an agent with unrestricted access to the same account. Keep
the source manifest and database outside candidate-writer filesystem access
when that boundary is required. The existing central HTTP mode uses
token-derived identities; this change does not replace that authentication.
Existing explicit administrative approval tools also remain available.

For the live acceptance run, configure Hermes as reader, Vibe as writer, and
the existing automated reviewer as a separate approver. Point all three at the
same absolute database path. Have the reviewer retrieve a pending candidate,
hash its returned content, and invoke `memory_review` (or CLI `review`) with
that revision. No human confirmation is required by the review operation.
This patch does not modify or schedule the separate OpenClaw reviewer.

Repeat the six steps with an actual project decision and independently retained
source evidence. Preserve the IDs, revisions, hashes and history before and
after restarting the actual clients. Only that run establishes desktop
integration. No production vault or Windows client was touched by the contract
test.

Rollback: stop using `memory_review`, disable its caller, and restore the prior
client configuration. There is no schema migration. Existing audit events and
links remain readable by the base layer. Reverting code does not reverse an
already promoted decision; submit a supported correction or restore a verified
backup into a separate database and check it before switching clients.

## Cloudflare pattern adaptation

The design borrows the separation between discovery, validation, structured
verdicts and final evidence from Cloudflare's
[security-audit-skill](https://github.com/cloudflare/security-audit-skill).
Here, discovery is candidate submission, validation compares the trusted source,
and the database independently rechecks the reviewed snapshot before committing.
The tests inspect results through another client and after process restart.

This is not a Cloudflare security-audit run or an independently verified
vulnerability report. Its full workflow requires fresh verifier agents and
OS-enforced execution isolation. Those requirements must be met separately
before claiming that workflow was executed. There are no vulnerability severity
claims in these memory review receipts.
