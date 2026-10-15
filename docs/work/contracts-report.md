# Foundation contracts report

## Owned scope

This work defines configuration, typed model outputs, workflow state vocabulary, role descriptors,
fixed prompts, configuration examples, and their unit tests. It does not perform persistence or
orchestration.

## Configuration contract

- `Config` is a strict Pydantic model with exactly five model roles: `background`, `brain`,
  `probe_manager`, `solver`, and `editor`.
- Every `ModelConfig` has `name`, `reasoning_effort`, and `verbosity`, plus optional nonnegative
  `input_usd_per_million` and `output_usd_per_million` estimates.
- Hard defaults are: 8 active branches, 4 concurrent branches, 3 probe rounds, 6 new branches per
  Brain cycle, 3 model attempts, 50 MB PDFs, no daily dollar cap, 10,000 model runs, 16,000 output
  tokens, and 160,000 context characters.
- Runtime defaults are a 300 second call timeout, 1 second retry base, and 900 second lease.
- Editor failure is fail-closed; open-access PDF downloading and tracing are enabled by default;
  the project root defaults to `projects`.
- `load_config(global_path, project_path)` deep-merges defaults, global YAML, then project YAML.
  `MATHAGENT_PROJECTS_ROOT` and `MATHAGENT_MODEL_<ROLE>` apply last. Unknown keys, unknown roles,
  missing roles after validation, malformed YAML, and nonpositive hard limits are rejected.

## Structured output contract

All structured output models forbid extra fields, and all list fields use independent empty-list
factories.

- `ArtifactDraft`: `kind`, `content`, and `editor_mode` (`aggressive`, `proof_safe`, or `prompt`).
  It has no path field.
- `LiteratureReference` and `BackgroundOutput` carry bibliography metadata and the four required
  drafts: problem specification, literature index, background report, and downstream context.
- `InsightProposal`, `InsightUpdate`, `BranchProposal`, and `BrainOutput` match the specified Brain
  control/prose split. A branch proposal references exactly one existing `parent_insight_id` or
  zero-based nonnegative `new_insight_index`; code later resolves the reference and creates IDs.
- `ProbeFormulation` states assumptions, forbidden assumptions, proof/disproof criteria, both
  strategic implications, relevance, and an artifact.
- `SolverOutput` accepts only `PROVED`, `DISPROVED`, or `INCONCLUSIVE`. A conclusive verdict requires
  nonblank `proof_or_counterexample`; an inconclusive verdict requires a nonblank `bottleneck`.
- `ProbeAssessment` accepts only `CONFIRM`, `REFUTE`, `PARTIAL`, `REFORMULATE`, `TOO_HARD`, or
  `ABANDON`. Reformulation requires `next_probe`; every terminal action forbids it. Confirm requires
  a proved Solver verdict and refute requires a disproved verdict. There is deliberately no
  model-authored `branch_status`; orchestration maps action to status and enforces the round limit.
- `EditorOutput` contains only edited prose and consistency warnings, so it cannot mutate control
  state.

## State and agent contract

- Enums define Brain-cycle, insight, branch, probe, Solver-verdict, and job values from the product
  specification.
- Terminal state sets are explicit. Legal Brain-cycle, branch, probe, and job transition tables are
  closed: a transition must be listed. `can_transition` dispatches by concrete enum type so equal
  text such as `QUEUED` cannot accidentally cross state machines.
- Role descriptors bind each role to its fixed prompt filename and typed output schema without any
  persistence or application-level handoff. Probe Manager exposes formulation as its primary and
  assessment as its secondary output schema. Only Background declares web-search capability.
- Prompts keep Solver context local, preserve mathematical quantifiers and epistemic status, force
  proof/disproof symmetry, keep IDs and paths code-owned, and give the Editor distinct aggressive,
  proof-safe, and prompt behavior.

## TDD and verification evidence

The initial contract test run failed during collection because the package did not exist, after the
shared environment finished installing pytest and Pydantic. After implementation:

```text
.venv/bin/python -m pytest tests/unit/test_contracts.py -q
14 passed in 0.14s
```

Static verification:

```text
.venv/bin/ruff check src/math_research_agent/config.py src/math_research_agent/schemas.py \
  src/math_research_agent/models.py src/math_research_agent/agents tests/unit/test_contracts.py
All checks passed!
```

Repository-wide integration verification is owned by the root task because those modules and tests
were still changing during this bounded contract implementation.
