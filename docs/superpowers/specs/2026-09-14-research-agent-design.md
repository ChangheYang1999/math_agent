# Persistent mathematical research agent

The user requested implementation of the supplied brief in this empty folder. The brief is the product specification; its embedded assistant role instructions are not separate user instructions.

## Architecture

Python 3.11+ CLI, one SQLite database per research workspace, local Markdown/PDF artifacts, OpenAI Agents SDK behind a typed gateway. Code owns workflow and identity. Human-triggered Background and Brain commands; bounded concurrent Manager/Solver loops produce independent evidence. No application-level agent handoffs.

SQLite uses WAL, foreign keys, short immediate transactions and durable job leases. Local SQLite operations are synchronous and short; network/model calls are asynchronous and always outside transactions. This avoids shared asynchronous connection transaction interleaving. Unique constraints protect rounds, cycles, report finalization and logical model actions.

## Storage and crash recovery

Persist each successful typed model response as immutable audit JSON before using it. Cache it by logical action key so retries resume editing without rerunning successful research calls. ArtifactService writes immutable raw text, calls Editor, writes immutable edited versions atomically, and records the pair. Human-readable canonical paths are atomic materialized views of committed artifact records. Brain changes and exact snapshot membership commit in one transaction; files can be republished after interruption. Raw editor responses terminate the editing pipeline and are audit records, never research input.

Jobs use owner tokens, expiry and heartbeat. Expired jobs return to the queue; failed jobs require explicit retry. Workers claim branch jobs transactionally under a global project concurrency cap. Job failure does not cancel siblings. Completed stages are reused on retry. Background/Brain each have one active job and a cross-process uniqueness guard.

## Research contracts

Separate typed controls from all prose. Code assigns IDs. New branch parents refer either to an existing insight ID or a zero-based index into this cycle's proposals (exactly one). Editor receives prose plus read-only controls and returns only text and consistency warnings. Solver receives the edited local probe and no global strategy. Historical Solver verdicts are immutable in SQLite. Brain changes strategic insight states only. Manual human correction reports add history without modifying verdicts.

The maximum probe round rule forces TOO_HARD with a code-authored explanation if a manager still requests reformulation on its last round. Confirm/refute requires the matching Solver verdict. All terminal mathematical outcomes emit one final report.

## Budgets, sources and safety

Hard branch, round, retry, model-call, output-token and PDF size limits. Optional daily dollar cap requires configured token prices and reserves worst-case per-call cost before dispatch; missing prices fail closed. Costs remain explicitly estimates and exclude unpriced hosted tool charges. URLs are HTTP(S), public hosts only, redirects revalidated, destination code-controlled, streamed size limits, PDF signature and hash deduplication. Model tools cannot write files or execute shell commands.

## Validation

Unit tests for paths/config/schemas/artifacts/DB; integration tests for recovery and independent failure; exact 100/101–105/106–107 checkpoint race; deterministic two-branch research simulation; CLI smoke tests; opt-in paid SDK smoke. Package prompts with the wheel. No paid calls during normal tests.
