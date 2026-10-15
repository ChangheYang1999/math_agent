# CLI, documentation, and offline demo report

## Owned scope

This subtask implements `src/math_research_agent/cli.py`,
`src/math_research_agent/demo.py`, `tests/integration/test_cli.py`, and the repository `README.md`.
It uses the orchestration, persistence, configuration, and gateway interfaces supplied by the root
task without modifying them.

## Command contract

- Global `--config FILE` and `--projects-root PATH` options precede the command. Configuration is
  validated even when the command-line root overrides the configured project root.
- `init <slug> --title TITLE` creates a real workspace and database without constructing a hosted
  gateway or requiring `OPENAI_API_KEY`.
- `problem set <slug> --file PATH` records a UTF-8 problem; `--file -` reads standard input.
- `background <slug>` and `brain <slug>` execute their explicit human-triggered workflows.
- `workers <slug> [--max-concurrent N]` runs bounded branch work. It prints every job ID, exits 1
  when any job fails, shows only the sanitized error class, and gives the retry ID.
- `branch run <slug> ID` executes one branch. `branch|insight|probe|report show <slug> ID` prints
  canonical content, raw audit paths, status, and remaining metadata without requiring a gateway.
- `status <slug>` prints a human summary including project, Brain cycle, last processed report,
  insight and branch state, inbox, and jobs. `--json` returns the complete orchestration status
  object, including usage, warnings, and downloads.
- `retry <slug> --job ID` explicitly retries and executes a failed infrastructure job. `recover`
  requeues expired leases and reconciles canonical files. Mathematical `INCONCLUSIVE` remains a
  result rather than an infrastructure failure.
- `correction <slug> --file PATH [--insight ID]` stores an immutable human correction as a new inbox
  report. It accepts standard input with `--file -`.
- Expected path, validation, SQLite, Editor, and model-gateway failures produce a concise exit-1
  message without a traceback. Pydantic errors identify the failing field without echoing the input.

## Offline demo contract

`demo [slug]` creates a new project through production initialization and uses the production
`FakeModelGateway`. Its packaged fixtures are elementary and deterministic; production code never
imports test fixtures. The run performs Background, Brain cycle 1, two concurrent branches, and
Brain cycle 2. Branch `B-000001` proves square nonnegativity and ends `CONFIRMED`; `B-000002`
disproves nonnegativity of every real number using `x = -1` and ends `REFUTED`. The synthetic
literature is explicitly labeled `[UNVERIFIED]`, and no API key or network is used.

## Documentation contract

The README includes the architecture and role boundaries; uv and standard-venv installation; API
key handling; verified command names; raw/canonical audit behavior; exact Brain snapshots;
concurrency and leases; status and inspection; retries, reconciliation, and human corrections;
configuration precedence and hard limits; estimated-cost limitations; tracing privacy; backups;
offline and live tests; current research limitations; and three concrete extensions. It explains
that all research workspaces are ignored by source control and defers Git export to a future
explicit allowlist feature.

## TDD and verification evidence

The first focused run failed all eight initial tests because `math_research_agent.cli` did not yet
exist. Subsequent red-green iterations caught the optional demo argument, actual status response
shape, labeled raw paths, scheduler error representation, last-processed-report display, and config
validation despite a command-line root override.

Fresh owned-scope verification after implementation:

```text
.venv/bin/python -m pytest tests/integration/test_cli.py -q
10 passed in 3.57s
```

```text
.venv/bin/ruff check src/math_research_agent/cli.py src/math_research_agent/demo.py \
  tests/integration/test_cli.py
All checks passed!
```

The module and optional demo argument help both exit successfully with `PYTHONPATH=src`. Repository
wide integration and formatting checks remain owned by the root task while concurrent service and
lease work is changing.
