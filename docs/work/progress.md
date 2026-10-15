# Implementation ledger
Plan: docs/superpowers/plans/2026-09-14-research-agent.md

Ruling: Implement directly in the requested empty folder, with no worktree relocation; there is no existing Git repository or user work to isolate.
Ruling: Use the supplied design and user request as authorization for implementation; do not reopen product decisions.
Ruling: SQLite short synchronous transactions are simpler to audit than sharing an async connection; no network work occurs inside them.
Ruling: Explicit new_insight_index removes ambiguity in proposals referencing insights that have no canonical IDs yet.

Interface review: schemas/config feed gateway and orchestration; Database and Paths feed all persistence. Agents never perform persistence. Jobs enclose orchestration; artifacts cache logical keys. Tasks 1–5 fit the specification; integration changes remain the root worker's responsibility.

Task 1: complete — configuration, schemas, roles/prompts, paths, IDs, migrations and persistence.
Task 2: complete — typed real/fake gateways, audit cache, mandatory editing, proof-safe mode, usage/tracing.
Task 3: complete — resumable branch loops, fencing leases, global concurrency cap, inbox and recovery.
Task 4: complete — fixed Brain snapshots, atomic strategy updates, formalization and safe literature downloads.
Task 5: complete — CLI, offline demo, 96 passing tests, opt-in live test, documentation, lockfile and wheel.

Review fixes: transaction-level lease fencing; no stale failure cleanup; atomic immutable publication;
new attempts for rejected Editor output; task-local artifact fencing; CLI never claims completion on
unclaimed jobs; startup recovery count; single SDK turn per budget reservation with schema overhead.
Additional acceptance fixes: parent insight/detailed paths in readable final reports; explicit
INCONCLUSIVE strategic criterion; standalone EDIT_ARTIFACT execution without premature publication.

Final verification: 96 passed, 1 deliberately skipped live test; Ruff and format checks pass; CLI
verified-demo completes; wheel builds and packages all role prompts. No paid API call or Git commit.
