# Research Agent Implementation Plan

> Execution: use Superpowers test-driven development and bounded delegated tasks, followed by review and verification.

**Goal:** Build the local persistent research CLI specified in the supplied brief.
**Architecture:** SQLite controls; artifacts carry edited mathematics; async Python orchestrates independent branches and manual Brain cycles.
**Tech Stack:** Python 3.11+, Pydantic, Typer, SQLite, httpx, PyYAML, OpenAI Agents SDK, pytest, Ruff.
**Spec:** docs/superpowers/specs/2026-09-14-research-agent-design.md and the user-supplied implementation brief.

## Global constraints

No web frontend, arbitrary model-chosen paths, recursive editor calls, heuristic status extraction, or paid calls in normal tests. Keep raw output immutable. Fail closed on editing failure. Never hold a DB transaction across a model call. All writes stay in this folder.

## Task 1: Foundation and contracts

Files: pyproject.toml; config.py; schemas.py; models.py; paths.py; ids.py; db.py; migrations.py; tests/unit/test_foundation.py; prompts/*.md.
- [x] Write failing tests for traversal, overrides, ID uniqueness, migrations and typed result validation.
- [x] Implement Config/load_config; typed role outputs; Paths.resolve; Database transaction/insert/query; generated IDs and schema constraints.
- [x] Run focused tests, verify independent database reopen and inspect schema.

## Task 2: Model and artifact boundary

Files: model_gateway.py; editor_service.py; artifacts.py; agents/*.py; tests/unit/test_artifacts.py; tests/unit/test_gateway.py.
- [x] Write failures demonstrating raw-before-edit and editor failure preserving recoverable raw artifacts.
- [x] Implement Gateway protocol and real/fake adapters; persist run metadata, prompt hashes, typed raw responses and successful action cache.
- [x] Implement persist(kind, scope, key, raw_content, mode, destination, metadata) returning an artifact row. Editor returns only edited_content and consistency_issues. Never pass raw cached prose to downstream agents.
- [x] Test retries, usage, proof-safe selection, atomic publishing, immutable records and editor control isolation.

## Task 3: Branch loop, jobs and inbox

Files: branches.py; jobs.py; scheduler.py; inbox.py; context_builder.py; tests/integration/test_branches.py.
- [x] Script Q1 INCONCLUSIVE → REFORMULATE → Q2 DISPROVED → REFUTE and assert transitions/files.
- [x] Implement sequential branch stages with cached calls and artifact recovery. Uniqueness protects branch rounds and final reports.
- [x] Implement leased claim/retry/recover, project-wide concurrent cap, independent failures.
- [x] Test last-round reformulation, failed editor retry, sibling isolation and restart without duplicate proof calls.

## Task 4: Brain and background

Files: brain.py; background.py; literature.py; orchestrator.py; tests/integration/test_brain.py; tests/unit/test_literature.py.
- [x] Write exact snapshot race with 101–105 present and 106–107 arriving during call.
- [x] Implement fixed membership snapshot, existing/new parent validation, branch budgets, all-prose editing, atomic state commit and rebuildable file publication.
- [x] Implement formalization/report/context/bibliography outputs and safe PDF downloads.
- [x] Verify Brain failure leaves all reports unprocessed and no partial strategic state.

## Task 5: CLI and complete validation

Files: cli.py; README.md; config.example.yaml; .env.example; tests/integration/test_e2e.py; tests/integration/test_cli.py; tests/test_live.py.
- [x] Write deterministic full two-branch simulation and CLI init/problem/status/inspect/retry tests.
- [x] Implement commands and a reproducible offline demo; add manual correction reports and opt-in live smoke.
- [x] Run all tests, Ruff, packaging/install/help, inspect source for secrets and unfinished functions, review implementation.
- [x] Document real commands, recovery boundaries, privacy/tracing, costs and next extensions.
