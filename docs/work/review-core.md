# Core correctness review

Reviewed persistence, paths, jobs, branch loops, Inbox, Brain, contexts, and orchestration. Production files were not changed. Focused validation: `11 passed` for branch/Brain integration tests and jobs/artifacts unit tests. The exact 101–107 checkpoint test passes; report membership is persisted and committed correctly. Verdict/raw-record triggers and edited downstream context selection look sound in their covered paths.

## P1 — Lease ownership does not fence workflow state mutations

Locations: `src/math_research_agent/orchestrator.py:79–86`; `src/math_research_agent/brain.py:95–99`; equivalent guard-then-write sequences in `branches.py` and `inbox.py:finalize_branch`.

`JobStore.fail` conditionally changes only the old owner's job, but `execute_job` then unconditionally marks its branch/cycle failed. Reproduced by expiring the first worker during its model callback, recovering and claiming the same job with a new owner, moving the replacement branch to `WAITING_FOR_SOLVER`, and then raising the old call's exception. Result: the replacement job remains `RUNNING` with its new lease token while its branch becomes `FAILED`. The replacement's next ordinary transition can fail; stale Brain cleanup can likewise rewrite the replacement cycle state.

Also, success guards run on separate connections before the write transaction. A process paused after a successful guard can resume after another process recovers/reclaims the lease and still commit probe changes, a final report, or the entire Brain cycle. Heartbeat cancellation does not close this cross-process race.

Minimal fix: make token verification and each workflow-state transaction atomic under the same `BEGIN IMMEDIATE` connection. Include job ID/token in the runner context or a fenced transaction helper. Move conditional job failure and related branch/cycle failure into one transaction, and only mutate the entity when that token still owns the job. Add takeover tests for both successful commit and failure cleanup, including a pause immediately after the old owner's guard.

## P2 — A rejected Editor response permanently poisons explicit retry

Location: `src/math_research_agent/editor_service.py:21–32`, interacting with the completed action cache in `model_gateway.py`.

The gateway persists/caches an `EditorOutput` as `COMPLETED` before EditorService checks nonempty prose and canonical IDs. If the Editor removes an ID, the artifact becomes `EDIT_FAILED`; every later retry requests the same `edit:{key}` and replays the same rejected result. A fresh corrected response can never be requested. Reproduced with the persistent `FakeModelGateway`: first Editor output drops `Q-000001.1`, second scripted output preserves it; two `ArtifactService.persist` attempts both raise `EditorFailure`, and the database still has exactly one completed editor run. Empty edited text has the same problem. Manager/Solver consistency checks after the gateway can create an analogous permanently cached rejection.

Minimal fix: preserve rejected raw responses as audit records while adding a bounded persisted validation-retry action key, or validate the complete role-specific contract before designating an action reusable. Explicit retry must be able to continue the edit without rerunning the successful research call. Test this using `FakeModelGateway`, rather than a transient network exception before a result is cached.

## P2 — Interrupted immutable writes expose partial final files

Location: `src/math_research_agent/paths.py:40–48`; particularly `brain.py:49–52` and the gateway's content-addressed prompt writes.

`write_immutable` opens the final pathname before writing. A process crash, full disk, or write error can leave a truncated file at that permanent name. Brain treats an existing context pathname as complete and consumes the truncated snapshot; a partial content-addressed prompt makes every subsequent gateway attempt fail its hash check. Reproduced by fault-injecting a write that writes five bytes and raises: the final context file remains `'{"cyc'`, and retrying the immutable write raises `FileExistsError`. No application recovery path repairs these files.

Minimal fix: write and fsync a temporary file in the same directory, atomically publish it without overwriting an existing destination (for example, an exclusive hard-link publication), fsync the parent directory, and clean up the temporary file. Keep immutability while ensuring final names only refer to complete content. Add an interrupted-write test asserting the final name is absent or contains the entire original value.
