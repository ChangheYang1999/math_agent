import asyncio
import hashlib
import json
from types import SimpleNamespace

import pytest
from agents import WebSearchTool

from math_research_agent.config import Config
from math_research_agent.db import Database
from math_research_agent.model_gateway import (
    FakeModelGateway,
    GatewayBudgetError,
    GatewayCacheError,
    GatewayInvocationError,
    GatewayLimitError,
    OpenAIModelGateway,
)
from math_research_agent.paths import Paths
from math_research_agent.schemas import EditorOutput


def make_db_and_paths(tmp_path):
    return Database.initialize(tmp_path, "test", "Test"), Paths(tmp_path)


@pytest.mark.asyncio
async def test_fake_gateway_persists_exact_prompt_typed_output_and_reuses_cache(tmp_path) -> None:
    db, paths = make_db_and_paths(tmp_path)
    calls = 0

    async def scripted(input_text, metadata):
        nonlocal calls
        calls += 1
        assert input_text == "edit this"
        assert metadata == {"branch_id": "B-000001"}
        return {"edited_content": "short", "consistency_issues": []}

    gateway = FakeModelGateway(
        db,
        paths,
        Config(),
        script={"edit:one": [scripted]},
    )
    first = await gateway.run_structured(
        role="editor",
        input_text="edit this",
        output_type=EditorOutput,
        action_key="edit:one",
        metadata={"branch_id": "B-000001"},
    )
    second = await gateway.run_structured(
        role="editor",
        input_text="ignored on recovery",
        output_type=EditorOutput,
        action_key="edit:one",
    )

    assert calls == 1
    assert second == first
    assert first.output == EditorOutput(edited_content="short")
    assert json.loads(paths.read(first.raw_path)) == {
        "edited_content": "short",
        "consistency_issues": [],
    }
    row = db.one("SELECT * FROM model_runs WHERE id=?", (first.run_id,))
    assert row is not None
    prompt = paths.read(row["prompt_path"])
    assert row["prompt_hash"] == hashlib.sha256(prompt.encode()).hexdigest()
    assert paths.resolve(row["prompt_path"]).name == f"{row['prompt_hash']}.md"
    assert row["status"] == "COMPLETED"
    assert row["scope_type"] == "branch"
    assert row["scope_id"] == "B-000001"


@pytest.mark.asyncio
async def test_fake_gateway_retries_failures_without_storing_provider_text(tmp_path) -> None:
    db, paths = make_db_and_paths(tmp_path)
    gateway = FakeModelGateway(
        db,
        paths,
        Config(
            limits={"max_model_attempts": 3},
            runtime={"retry_base_seconds": 0},
        ),
        script={
            "edit:retry": [
                RuntimeError("provider secret sk-do-not-store"),
                {"wrong": "shape"},
                {"edited_content": "valid"},
            ]
        },
    )

    result = await gateway.run_structured(
        role="editor",
        input_text="x",
        output_type=EditorOutput,
        action_key="edit:retry",
    )

    assert result.output.edited_content == "valid"
    rows = db.query("SELECT status,error,raw_output_path FROM model_runs ORDER BY started_at,id")
    assert [row["status"] for row in rows].count("FAILED") == 2
    assert [row["status"] for row in rows].count("COMPLETED") == 1
    stored_errors = " ".join(row["error"] or "" for row in rows)
    assert "sk-do-not-store" not in stored_errors
    assert "provider secret" not in stored_errors
    invalid_rows = [row for row in rows if row["status"] == "FAILED" and row["raw_output_path"]]
    assert len(invalid_rows) == 1
    assert json.loads(paths.read(invalid_rows[0]["raw_output_path"])) == {"wrong": "shape"}


@pytest.mark.asyncio
async def test_gateway_timeout_is_bounded_and_audited_without_exception_text(tmp_path) -> None:
    db, paths = make_db_and_paths(tmp_path)

    async def too_slow(input_text, metadata):
        await asyncio.sleep(2)
        return {"edited_content": "late"}

    gateway = FakeModelGateway(
        db,
        paths,
        Config(
            limits={"max_model_attempts": 1},
            runtime={"timeout_seconds": 1, "retry_base_seconds": 0},
        ),
        script={"edit:slow": [too_slow]},
    )

    with pytest.raises(GatewayInvocationError, match="failed after 1 attempts"):
        await gateway.run_structured(
            role="editor",
            input_text="x",
            output_type=EditorOutput,
            action_key="edit:slow",
        )

    row = db.one("SELECT status,error FROM model_runs WHERE action_key='edit:slow'")
    assert row == {"status": "FAILED", "error": "Model invocation timed out"}


@pytest.mark.asyncio
async def test_fake_editor_default_removes_redundant_marker(tmp_path) -> None:
    db, paths = make_db_and_paths(tmp_path)
    gateway = FakeModelGateway(db, paths, Config())

    result = await gateway.run_structured(
        role="editor",
        input_text=json.dumps({"raw_content": "Keep. REDUNDANT Remove marker."}),
        output_type=EditorOutput,
        action_key="edit:default",
    )

    assert result.output == EditorOutput(edited_content="Keep. Remove marker.")


@pytest.mark.asyncio
async def test_completed_cache_is_revalidated_against_requested_type(tmp_path) -> None:
    db, paths = make_db_and_paths(tmp_path)
    gateway = FakeModelGateway(
        db,
        paths,
        Config(),
        script={"same-action": [{"edited_content": "valid"}]},
    )
    await gateway.run_structured(
        role="editor",
        input_text="x",
        output_type=EditorOutput,
        action_key="same-action",
    )

    class DifferentOutput(EditorOutput):
        required_new_field: str

    with pytest.raises(GatewayCacheError):
        await gateway.run_structured(
            role="editor",
            input_text="x",
            output_type=DifferentOutput,
            action_key="same-action",
        )


@pytest.mark.asyncio
async def test_gateway_enforces_context_and_project_run_caps_before_invocation(tmp_path) -> None:
    db, paths = make_db_and_paths(tmp_path)
    called = 0

    async def scripted(input_text, metadata):
        nonlocal called
        called += 1
        return {"edited_content": "ok"}

    context_gateway = FakeModelGateway(
        db,
        paths,
        Config(limits={"max_context_chars": 1}),
        script={"too-long": [scripted]},
    )
    with pytest.raises(GatewayLimitError, match="context"):
        await context_gateway.run_structured(
            role="editor",
            input_text="two characters",
            output_type=EditorOutput,
            action_key="too-long",
        )
    assert called == 0

    capped_gateway = FakeModelGateway(
        db,
        paths,
        Config(limits={"max_model_runs": 1}),
        script={"first": [scripted], "second": [scripted]},
    )
    await capped_gateway.run_structured(
        role="editor", input_text="x", output_type=EditorOutput, action_key="first"
    )
    with pytest.raises(GatewayLimitError, match="run"):
        await capped_gateway.run_structured(
            role="editor", input_text="x", output_type=EditorOutput, action_key="second"
        )
    assert called == 1


@pytest.mark.asyncio
async def test_daily_cap_fails_closed_when_any_model_price_is_missing(tmp_path) -> None:
    db, paths = make_db_and_paths(tmp_path)
    called = False

    async def scripted(input_text, metadata):
        nonlocal called
        called = True
        return {"edited_content": "unreachable"}

    gateway = FakeModelGateway(
        db,
        paths,
        Config(limits={"daily_budget_usd": 10}),
        script={"priced": [scripted]},
    )

    with pytest.raises(GatewayBudgetError, match="prices"):
        await gateway.run_structured(
            role="editor", input_text="x", output_type=EditorOutput, action_key="priced"
        )
    assert called is False
    assert db.query("SELECT * FROM model_runs") == []


@pytest.mark.asyncio
async def test_daily_cap_reserves_worst_case_inside_audited_attempt(tmp_path) -> None:
    db, paths = make_db_and_paths(tmp_path)
    models = Config().model_dump(mode="python")["models"]
    for model in models.values():
        model["input_usd_per_million"] = 1.0
        model["output_usd_per_million"] = 2.0
    config = Config(
        models=models,
        limits={"daily_budget_usd": 0.001, "max_output_tokens": 1000},
    )
    gateway = FakeModelGateway(
        db,
        paths,
        config,
        script={"over-budget": [{"edited_content": "unreachable"}]},
    )

    with pytest.raises(GatewayBudgetError, match="budget"):
        await gateway.run_structured(
            role="editor", input_text="x", output_type=EditorOutput, action_key="over-budget"
        )
    assert db.query("SELECT * FROM model_runs") == []


@pytest.mark.asyncio
async def test_known_usage_replaces_reservation_for_failed_and_successful_calls(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, paths = make_db_and_paths(tmp_path)
    models = Config().model_dump(mode="python")["models"]
    for model in models.values():
        model["input_usd_per_million"] = 1.0
        model["output_usd_per_million"] = 2.0
    calls = 0

    class StubRunner:
        @staticmethod
        async def run(agent, input_text, *, run_config, max_turns):
            assert max_turns == 1
            nonlocal calls
            calls += 1
            output = {"wrong": "shape"} if calls == 1 else {"edited_content": "valid"}
            return SimpleNamespace(
                final_output=output,
                context_wrapper=SimpleNamespace(
                    usage=SimpleNamespace(input_tokens=11, output_tokens=7, total_tokens=18)
                ),
            )

    import math_research_agent.model_gateway as gateway_module

    monkeypatch.setattr(gateway_module, "Runner", StubRunner)
    gateway = OpenAIModelGateway(
        db,
        paths,
        Config(
            models=models,
            limits={"daily_budget_usd": 1, "max_model_attempts": 2},
            runtime={"retry_base_seconds": 0},
        ),
    )
    await gateway.run_structured(
        role="editor", input_text="x", output_type=EditorOutput, action_key="known-usage"
    )

    rows = db.query(
        "SELECT status,estimated_cost_usd,reserved_cost_usd FROM model_runs ORDER BY started_at,id"
    )
    assert {row["status"] for row in rows} == {"FAILED", "COMPLETED"}
    for row in rows:
        assert row["estimated_cost_usd"] == pytest.approx(0.000025)
        assert row["reserved_cost_usd"] == 0


@pytest.mark.asyncio
async def test_openai_gateway_uses_sdk_structured_agent_tools_settings_usage_and_safe_tracing(
    tmp_path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    db, paths = make_db_and_paths(tmp_path)
    captured = []

    class StubRunner:
        @staticmethod
        async def run(agent, input_text, *, run_config, max_turns):
            assert max_turns == 1
            captured.append((agent, input_text, run_config))
            return SimpleNamespace(
                final_output=EditorOutput(edited_content="from sdk"),
                context_wrapper=SimpleNamespace(
                    usage=SimpleNamespace(input_tokens=11, output_tokens=7, total_tokens=18)
                ),
            )

    import math_research_agent.model_gateway as gateway_module

    monkeypatch.setattr(gateway_module, "Runner", StubRunner)
    caplog.set_level("INFO", logger="math_research_agent.model_gateway")
    gateway = OpenAIModelGateway(db, paths, Config(tracing={"enabled": False}))
    result = await gateway.run_structured(
        role="background",
        input_text="find papers",
        output_type=EditorOutput,
        action_key="background:one",
        metadata={
            "project": "test",
            "cycle": "C-000003",
            "branch": "B-000001",
            "probe": "Q-000001.1",
            "job": "J-000009",
            "api_key": "sk-must-not-be-exported",
        },
    )

    assert result.output.edited_content == "from sdk"
    agent, input_text, run_config = captured[0]
    assert input_text == "find papers"
    assert agent.output_type is EditorOutput
    assert agent.model == Config().models["background"].name
    assert agent.model_settings.reasoning.effort == "high"
    assert agent.model_settings.verbosity == "low"
    assert agent.model_settings.max_tokens == Config().limits.max_output_tokens
    assert len(agent.tools) == 1 and isinstance(agent.tools[0], WebSearchTool)
    assert run_config.group_id == "B-000001"
    assert run_config.tracing_disabled is True
    assert run_config.trace_include_sensitive_data is False
    assert run_config.trace_metadata["probe"] == "Q-000001.1"
    assert run_config.trace_metadata["job"] == "J-000009"
    assert "api_key" not in run_config.trace_metadata
    assert "B-000001" in caplog.text
    assert "C-000003" in caplog.text
    assert "Q-000001.1" in caplog.text
    assert "J-000009" in caplog.text
    assert "sk-must-not-be-exported" not in caplog.text
    row = db.one("SELECT * FROM model_runs WHERE id=?", (result.run_id,))
    assert row is not None
    assert (row["input_tokens"], row["output_tokens"], row["total_tokens"]) == (11, 7, 18)
    assert row["estimated_cost_usd"] is None


@pytest.mark.asyncio
async def test_unknown_usage_success_and_concurrent_loser_keep_cost_reservations(tmp_path) -> None:
    db, paths = make_db_and_paths(tmp_path)
    models = Config().model_dump(mode="python")["models"]
    for model in models.values():
        model["input_usd_per_million"] = 1.0
        model["output_usd_per_million"] = 2.0
    config = Config(
        models=models,
        limits={"daily_budget_usd": 1, "max_model_attempts": 1},
    )
    both_invoking = asyncio.Event()
    invocation_count = 0

    async def rendezvous(input_text, metadata):
        nonlocal invocation_count
        invocation_count += 1
        if invocation_count == 2:
            both_invoking.set()
        await asyncio.wait_for(both_invoking.wait(), timeout=1)
        return {"edited_content": "same"}

    first_gateway = FakeModelGateway(db, paths, config, script={"race": [rendezvous]})
    second_gateway = FakeModelGateway(db, paths, config, script={"race": [rendezvous]})
    first, second = await asyncio.gather(
        first_gateway.run_structured(
            role="editor", input_text="x", output_type=EditorOutput, action_key="race"
        ),
        second_gateway.run_structured(
            role="editor", input_text="x", output_type=EditorOutput, action_key="race"
        ),
    )

    assert first == second
    rows = db.query("SELECT status,reserved_cost_usd FROM model_runs")
    assert {row["status"] for row in rows} == {"COMPLETED", "FAILED"}
    assert all(row["reserved_cost_usd"] > 0 for row in rows)


@pytest.mark.asyncio
async def test_non_background_sdk_agent_has_no_tools(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, paths = make_db_and_paths(tmp_path)
    seen_tools = None

    class StubRunner:
        @staticmethod
        async def run(agent, input_text, *, run_config, max_turns):
            assert max_turns == 1
            nonlocal seen_tools
            seen_tools = agent.tools
            return SimpleNamespace(
                final_output={"edited_content": "ok"},
                context_wrapper=SimpleNamespace(
                    usage=SimpleNamespace(input_tokens=0, output_tokens=0, total_tokens=0)
                ),
            )

    import math_research_agent.model_gateway as gateway_module

    monkeypatch.setattr(gateway_module, "Runner", StubRunner)
    await OpenAIModelGateway(db, paths, Config()).run_structured(
        role="editor", input_text="x", output_type=EditorOutput, action_key="editor:no-tools"
    )

    assert seen_tools == []


@pytest.mark.parametrize(
    ("attempts", "run_cap", "budget", "expected_error", "expected_calls"),
    [
        (1, 10, 1.0, GatewayInvocationError, 1),
        (2, 1, 1.0, GatewayLimitError, 1),
        (2, 10, 0.000015, GatewayBudgetError, 1),
        (2, 2, 1.0, None, 2),
    ],
)
async def test_real_sdk_continuation_requires_a_separately_reserved_attempt(
    tmp_path, monkeypatch, attempts, run_cap, budget, expected_error, expected_calls
):
    """Use the real Runner: replacing it would hide its automatic continuation loop."""
    from agents import Agent
    from agents.items import ModelResponse
    from agents.models.interface import Model
    from agents.usage import Usage
    from openai.types.responses import ResponseOutputMessage, ResponseOutputText

    import math_research_agent.model_gateway as gateway_module

    class TwoTurnModel(Model):
        def __init__(self):
            self.calls = 0

        async def get_response(self, *args, **kwargs):
            self.calls += 1
            output = []
            if self.calls > 1:
                output = [
                    ResponseOutputMessage(
                        id="message-2",
                        type="message",
                        role="assistant",
                        status="completed",
                        content=[
                            ResponseOutputText(
                                type="output_text",
                                annotations=[],
                                text='{"edited_content":"ok","consistency_issues":[]}',
                            )
                        ],
                    )
                ]
            return ModelResponse(
                output=output,
                response_id=str(self.calls),
                usage=Usage(requests=1, input_tokens=0, output_tokens=10, total_tokens=10),
            )

        def stream_response(self, *args, **kwargs):
            raise AssertionError("This test only uses nonstreamed model calls")

    model = TwoTurnModel()

    def agent_with_offline_model(**kwargs):
        return Agent(**{**kwargs, "model": model})

    monkeypatch.setattr(gateway_module, "Agent", agent_with_offline_model)
    db, paths = make_db_and_paths(tmp_path)
    config = Config(
        limits={
            "max_model_attempts": attempts,
            "max_model_runs": run_cap,
            "max_output_tokens": 10,
            "daily_budget_usd": budget,
        },
        runtime={"retry_base_seconds": 0},
        tracing={"enabled": False},
    )
    for settings in config.models.values():
        settings.input_usd_per_million = 0
        settings.output_usd_per_million = 1
    gateway = OpenAIModelGateway(db, paths, config)
    invocation = gateway.run_structured(
        role="editor",
        input_text="x",
        output_type=EditorOutput,
        action_key="one",
    )
    if expected_error is not None:
        with pytest.raises(expected_error):
            await invocation
    else:
        assert (await invocation).output.edited_content == "ok"
    assert model.calls == expected_calls
    rows = db.query("SELECT * FROM model_runs ORDER BY started_at,id")
    assert len(rows) == expected_calls
    failed = [row for row in rows if row["status"] == "FAILED"]
    assert len(failed) == 1
    assert failed[0]["reserved_cost_usd"] == pytest.approx(0.00001)
    if expected_error is None:
        completed = next(row for row in rows if row["status"] == "COMPLETED")
        assert completed["output_tokens"] == 10
        assert completed["estimated_cost_usd"] == pytest.approx(0.00001)


async def test_output_schema_counts_toward_context_and_input_budget(tmp_path):
    from math_research_agent.model_gateway import _load_prompt

    db, paths = make_db_and_paths(tmp_path)
    prompt = _load_prompt("editor.md")
    context_config = Config(limits={"max_context_chars": len(prompt) + 1})
    gateway = FakeModelGateway(db, paths, context_config, {"one": [{"edited_content": "ok"}]})
    with pytest.raises(GatewayLimitError, match="context"):
        await gateway.run_structured(
            role="editor",
            input_text="x",
            output_type=EditorOutput,
            action_key="one",
        )
    # Exactly the prose-only reservation fits; the required response schema makes it exceed.
    config = Config(limits={"daily_budget_usd": (len(prompt.encode()) + 1) / 1_000_000})
    for settings in config.models.values():
        settings.input_usd_per_million = 1
        settings.output_usd_per_million = 0
    gateway = FakeModelGateway(db, paths, config, {"one": [{"edited_content": "ok"}]})
    with pytest.raises(GatewayBudgetError, match="budget"):
        await gateway.run_structured(
            role="editor",
            input_text="x",
            output_type=EditorOutput,
            action_key="one",
        )
    assert not db.query("SELECT * FROM model_runs")
