# Gateway and literature handoff

## Owned implementation

- `src/math_research_agent/model_gateway.py`
  - Public `ModelResult[T]`, `ModelGateway` protocol, `OpenAIModelGateway`, and
    `FakeModelGateway`.
  - Loads fixed role prompts without runtime mutation and writes the exact prompt once at
    `raw/prompts/<sha256>.md`.
  - Writes every returned provider payload as immutable JSON at
    `raw/model_runs/<run_id>.json` before typed validation. Valid responses are then marked
    complete; invalid structured responses retain their raw audit JSON on a failed attempt.
  - Reuses a completed `action_key` after validating the stored JSON against the currently
    requested output type. Fake scripts are consumed only when no completed cache entry exists.
  - Creates an Agents SDK `Agent` with the configured Responses model, reasoning effort,
    verbosity, structured `output_type`, and output-token cap. Only the Background role receives
    `WebSearchTool`; no role receives shell or filesystem tools.
  - Accepts both orchestrator metadata names (`project`, `cycle`, `branch`, `probe`, `job`) and the
    earlier `*_id` aliases. It uses `RunConfig` for branch/cycle grouping, exports only those safe
    identifiers as trace metadata, honors configured trace enablement, and always sets
    `trace_include_sensitive_data=False`. Each attempt logs only the same identifiers and role.
  - Enforces an overall invocation timeout and bounded exponential retries. Provider exception
    messages and structured validation payloads are never stored in `model_runs.error`.
  - Enforces project-wide model-run count inside the reservation transaction.
  - When a daily dollar cap is configured, requires input and output prices for every role and
    reserves the conservative byte-count input plus `max_output_tokens` before each attempt.
    Known usage replaces the reservation with the token-derived estimate. Unknown-usage success,
    failed calls, and concurrent successful-action losers retain their conservative reservation
    because the paid call may have been consumed. Estimates exclude hosted-tool fees.
  - The default fake Editor removes the literal `REDUNDANT ` marker from input JSON
    `raw_content`; every other unscripted fake role fails closed.

- `src/math_research_agent/literature.py`
  - Public `PDFDownloader`, `DownloadResult`, and `DownloadError`.
  - Accepts only credential-free HTTP(S), resolves every hostname, rejects any non-public DNS
    answer or private/local IP literal, and pins the validated public IP as the actual connection
    target. The request retains the logical host in its HTTP `Host` header and TLS SNI, closing the
    DNS rebinding gap between validation and connection.
  - Resolves relative redirects against the logical current URL, then repeats public-host
    validation and address pinning independently for every hop.
  - Uses a total operation timeout even with an injected offline test client. Its own client also
    disables proxy environment discovery with `trust_env=False`.
  - Streams with both declared and observed size checks, requires `%PDF-`, hashes the bytes, and
    writes only after all validation passes.
  - Stores PDFs at `literature/papers/<sha256>.pdf`, making deduplication independent of an
    untrusted or inconsistent filename hint. An existing hash path is verified before reuse.
  - Per-paper failures raise `DownloadError`; the Background orchestration layer can record that
    error and continue with the remaining references.

- `tests/unit/test_gateway.py`, `tests/unit/test_literature.py`, `tests/test_live.py`
  - Unit coverage uses the real persistence boundary and real SDK `Agent` construction while
    replacing only `Runner` network execution.
  - The paid smoke is skipped unless `RUN_OPENAI_SMOKE_TEST=1` is set.

## Public contracts for callers

```python
result = await gateway.run_structured(
    role="solver",
    input_text=edited_probe,
    output_type=SolverOutput,
    action_key="branch:B-000001:solve:1",
    metadata={"branch_id": "B-000001", "probe_id": "Q-000001.1"},
)
# result.output: SolverOutput
# result.run_id: model_runs.id
# result.raw_path: project-relative immutable JSON path
```

Fake script lookup prefers exact `action_key`, then `role`. Each value may be a dictionary, a
Pydantic value, an exception, or a sync/async callable with `(input_text, metadata)` arguments.

Gateway control failures use `GatewayLimitError`, `GatewayBudgetError`, and `GatewayCacheError`.
Exhausted model/validation retries use `GatewayInvocationError`. All inherit `GatewayError`.

```python
download = await PDFDownloader(paths, config).download(reference.pdf_url, reference.title)
# download.relative_path, download.sha256, download.size_bytes, download.url
```

## SDK references checked

Implementation was matched against OpenAI Agents SDK 0.22.2 source installed in `.venv` and the
official documentation for [agents and typed outputs](https://openai.github.io/openai-agents-python/agents/),
[runner configuration](https://openai.github.io/openai-agents-python/running_agents/),
[usage accounting](https://openai.github.io/openai-agents-python/usage/),
[hosted web search](https://openai.github.io/openai-agents-python/tools/), and
[sensitive-data tracing controls](https://openai.github.io/openai-agents-python/tracing/).

## Verification

```text
.venv/bin/python -m pytest tests/unit/test_gateway.py tests/unit/test_literature.py tests/test_live.py -q
# 24 passed, 1 skipped

.venv/bin/ruff check src/math_research_agent/model_gateway.py src/math_research_agent/literature.py tests/unit/test_gateway.py tests/unit/test_literature.py tests/test_live.py
# All checks passed!
```

The live test is intentionally excluded from normal paid execution by its environment guard. At
handoff, the repository-wide test run reached 52 passing and 1 skipped test, with 8 CLI tests
failing because `src/math_research_agent/cli.py` had not yet landed from the concurrent CLI task.
Repository-wide Ruff findings were likewise confined to concurrently owned files.

The final downloader safety pass was verified separately with 14 passing literature tests and a
clean Ruff check for `literature.py` and `test_literature.py`; no repository-wide run was performed
during the concurrent integration pass.
