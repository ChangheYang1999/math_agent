# Final project review

Reviewed source, tests, configuration, README, and the user brief after the persistence/recovery fixes. The mandatory production-fake end-to-end test includes two branches, reformulation, reopening the database, both terminal outcomes, both Brain cycles, and correction history. The prior lease fencing, Editor retry, and interrupted immutable-write findings have corresponding fixes and regression coverage. No production files were changed during this review; whole-suite/package verification is being run separately by the implementing agent.

## P1 — SDK continuation bypasses model-run and dollar limits

Location: `src/math_research_agent/model_gateway.py:366–377`.

One gateway attempt reserves the cost of one model response and creates one `model_runs` row, but `Runner.run` uses its default limit of ten turns. The actual SDK continues when a structured-output model response has no final text; it can therefore make additional paid model calls without another reservation, model-run limit check, or per-call output accounting. This also contradicts the README's stated output-token limit per run and worst-case reservation behavior.

**Reproduced without network using the real installed SDK Runner** and a custom SDK `Model`: first `get_response` returned no final text with 10 output tokens; the second returned a valid `EditorOutput` with 10 output tokens. Configured `max_model_runs=1`, `max_output_tokens=10`, daily budget `$0.000015`, zero input price and `$1/million` output price. Result: two model calls, one completed model-run record with 20 output tokens and `$0.000020` estimated cost. The configured daily cap was exceeded before code could reject anything. Existing boundary tests replace `Runner.run` entirely, so they do not exercise this continuation.

**Minimal fix:** use `max_turns=1` so each application attempt corresponds to at most one SDK model turn, leaving bounded retries to the gateway; alternatively add reservation, accounting, and audit hooks around every SDK model turn. Add a real-Runner/offline-Model regression that checks the second call is not dispatched without its own budget check. Preserve usage/reservation when the SDK exits due to the turn limit.

## P2 — Failed or unclaimed jobs are printed as completed

Locations: `src/math_research_agent/orchestrator.py:77–79`; `src/math_research_agent/cli.py:128–130` and the branch/worker/retry command output.

`execute_job` returns `None` whenever claiming fails, including an already failed job, another worker owning it, or the concurrency cap being full. The CLI formats every `None` as `completed` and generally exits zero. **Reproduced:** create a branch and its job both in `FAILED`, invoke `mathagent ... branch run test B-000001`; output is `Branch B-000001: completed`, exit status is `0`, and the database job remains `FAILED`. A retry that successfully requeues but cannot claim because other workers fill the concurrency cap similarly claims completion while leaving the job queued.

**Minimal fix:** distinguish completed, already running, queued due to capacity, and failed-needs-retry outcomes. Return a typed/no-claim result or inspect the job's resulting state before printing; failed jobs should produce an actionable error naming the retry job ID, and queued/running jobs should never be labeled completed. Add CLI tests with real database/job states rather than mocking successful return values.

## Verified disposition after fixes

- **SDK continuation finding: resolved.** `Runner.run(max_turns=1)` bounds each application attempt to one model turn. Real-Runner/offline-Model regressions verify the attempt limit, model-run limit, dollar cap, and separately reserved successful retry. The response schema now contributes to the input/context estimate. Gateway, end-to-end, and recovery verification passed: **22 tests**.
- **CLI false completion finding: resolved.** Unclaimed noncompleted jobs now raise `JobUnavailableError`; completed jobs return their saved result. The scheduler labels unavailable work deferred and the CLI prints `not run`. The real failed-branch regression passes with exit status 1 and retry guidance. Additional database-backed CLI checks confirmed that a capacity-blocked worker leaves its job queued and prints `not run`; a capacity-blocked retry exits 1 and reports `QUEUED`; replaying a completed branch returns its saved report ID. Recovery also reports jobs already recovered during application startup.
- **Prior rejected-Editor cache finding: resolved.** Persisted edit-attempt numbers select a new Editor action after rejection while retaining the original raw artifact. The persistent-gateway regression successfully replaces the rejected edit on retry. Task-local ownership checks prevent an expired worker from publishing an Editor result; standalone editing does not publish an uncommitted strategy.
- **Prior partial immutable-write finding: resolved.** Immutable publication links a fully written, synced temporary file into the final name without replacing existing content. Fault injection confirms a failure before publication exposes no final file and a retry succeeds; ordinary immutability and canonical replacement tests pass.

Final scoped verification: `tests/integration/test_cli.py`, `tests/integration/test_recovery_regressions.py`, `tests/unit/test_foundation.py`, and `tests/unit/test_artifacts.py`: **23 passed**. No production files changed during this final scoped re-review. No unresolved findings remain in these reviewed fixes; whole-project verification is reported separately by the implementing agent.
