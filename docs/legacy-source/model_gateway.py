"""Typed, audited boundary around model invocation."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import sqlite3
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Generic, Protocol, TypeVar
from uuid import uuid4

from agents import Agent, ModelSettings, RunConfig, Runner, WebSearchTool
from agents.agent_output import AgentOutputSchema
from pydantic import TypeAdapter, ValidationError

from .agents import ROLE_DESCRIPTORS
from .config import Config, ModelConfig
from .db import Database
from .execution import run_metadata
from .paths import Paths
from .schemas import EditorOutput

T = TypeVar("T")
logger = logging.getLogger(__name__)


class GatewayError(RuntimeError):
    """Base class for safe, user-facing gateway failures."""


class GatewayLimitError(GatewayError):
    """A hard context or model-run limit would be exceeded."""


class GatewayBudgetError(GatewayError):
    """A configured cost cap cannot be safely honored."""


class GatewayCacheError(GatewayError):
    """A completed cached response cannot satisfy its typed contract."""


class GatewayInvocationError(GatewayError):
    """All permitted provider or structured-output attempts failed."""


@dataclass(frozen=True)
class ModelResult(Generic[T]):
    output: T
    run_id: str
    raw_path: str


class ModelGateway(Protocol):
    async def run_structured(
        self,
        *,
        role: str,
        input_text: str,
        output_type: type[T],
        action_key: str,
        metadata: dict[str, str] | None = None,
    ) -> ModelResult[T]: ...


@dataclass(frozen=True)
class _Invocation:
    output: Any
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class _PersistentGateway:
    def __init__(self, db: Database, paths: Paths, config: Config) -> None:
        self.db = db
        self.paths = paths
        self.config = config

    async def run_structured(
        self,
        *,
        role: str,
        input_text: str,
        output_type: type[T],
        action_key: str,
        metadata: dict[str, str] | None = None,
    ) -> ModelResult[T]:
        if role not in ROLE_DESCRIPTORS or role not in self.config.models:
            raise ValueError(f"Unknown model role: {role}")
        if not action_key.strip():
            raise ValueError("action_key must be nonempty")

        cached = self._cached(action_key, output_type)
        if cached is not None:
            return cached

        prompt = _load_prompt(ROLE_DESCRIPTORS[role].prompt_filename)
        output_schema_json = _output_schema_json(output_type)
        if (
            len(prompt) + len(input_text) + len(output_schema_json)
            > self.config.limits.max_context_chars
        ):
            raise GatewayLimitError("Model context exceeds the configured character limit")
        prompt_hash, prompt_path = self._persist_prompt(prompt)
        safe_metadata = {**(metadata or {}), **run_metadata()}
        model_config = self.config.models[role]
        self._validate_pricing()

        for attempt in range(self.config.limits.max_model_attempts):
            trace_id = f"trace_{uuid4().hex}"
            run_id = uuid4().hex
            reservation = self._reserve_attempt(
                run_id=run_id,
                role=role,
                action_key=action_key,
                model_config=model_config,
                prompt=prompt,
                input_text=input_text,
                output_schema_json=output_schema_json,
                prompt_hash=prompt_hash,
                prompt_path=prompt_path,
                trace_id=trace_id,
                metadata=safe_metadata,
            )
            invocation: _Invocation | None = None
            try:
                _log_invocation(self.db.project["slug"], role, safe_metadata)
                invocation = await asyncio.wait_for(
                    self._invoke(
                        role=role,
                        input_text=input_text,
                        output_type=output_type,
                        action_key=action_key,
                        prompt=prompt,
                        model_config=model_config,
                        trace_id=trace_id,
                        metadata=safe_metadata,
                    ),
                    timeout=float(self.config.runtime.timeout_seconds),
                )
                raw_path = f"raw/model_runs/{run_id}.json"
                raw_json = TypeAdapter(Any).dump_json(invocation.output)
                self.paths.write_immutable(raw_path, raw_json)
                self.db.execute(
                    "UPDATE model_runs SET raw_output_path=? WHERE id=?", (raw_path, run_id)
                )
                output = TypeAdapter(output_type).validate_python(invocation.output)
                estimated_cost = _actual_cost(invocation, model_config)
                remaining_reservation = reservation if estimated_cost is None else 0.0
                try:
                    self.db.execute(
                        "UPDATE model_runs SET status='COMPLETED',completed_at=CURRENT_TIMESTAMP,"
                        "input_tokens=?,output_tokens=?,total_tokens=?,estimated_cost_usd=?,"
                        "reserved_cost_usd=?,raw_output_path=? WHERE id=?",
                        (
                            invocation.input_tokens,
                            invocation.output_tokens,
                            invocation.total_tokens,
                            estimated_cost,
                            remaining_reservation,
                            raw_path,
                            run_id,
                        ),
                    )
                except sqlite3.IntegrityError:
                    loser_reservation = reservation if estimated_cost is None else 0.0
                    self.db.execute(
                        "UPDATE model_runs SET status='FAILED',completed_at=CURRENT_TIMESTAMP,"
                        "error='Concurrent action already completed',input_tokens=?,output_tokens=?,"
                        "total_tokens=?,estimated_cost_usd=?,reserved_cost_usd=? WHERE id=?",
                        (
                            invocation.input_tokens,
                            invocation.output_tokens,
                            invocation.total_tokens,
                            estimated_cost,
                            loser_reservation,
                            run_id,
                        ),
                    )
                    winner = self._cached(action_key, output_type)
                    if winner is None:
                        raise
                    return winner
                return ModelResult(output=output, run_id=run_id, raw_path=raw_path)
            except Exception as exc:
                self._record_failure(
                    run_id,
                    exc,
                    reservation=reservation,
                    invocation=invocation,
                    model_config=model_config,
                )
                if attempt + 1 < self.config.limits.max_model_attempts:
                    delay = float(self.config.runtime.retry_base_seconds) * (2**attempt)
                    if delay:
                        await asyncio.sleep(delay)

        raise GatewayInvocationError(
            f"Model invocation failed after {self.config.limits.max_model_attempts} attempts"
        ) from None

    async def _invoke(
        self,
        *,
        role: str,
        input_text: str,
        output_type: type[T],
        action_key: str,
        prompt: str,
        model_config: ModelConfig,
        trace_id: str,
        metadata: dict[str, str],
    ) -> _Invocation:
        raise NotImplementedError

    def _cached(self, action_key: str, output_type: type[T]) -> ModelResult[T] | None:
        row = self.db.one(
            "SELECT id,raw_output_path FROM model_runs WHERE action_key=? AND status='COMPLETED'",
            (action_key,),
        )
        if row is None:
            return None
        raw_path = row["raw_output_path"]
        if not raw_path:
            raise GatewayCacheError("Completed model response has no audit path")
        try:
            payload = json.loads(self.paths.read(raw_path))
            output = TypeAdapter(output_type).validate_python(payload)
        except (OSError, ValueError, ValidationError):
            raise GatewayCacheError(
                "Completed model response failed typed cache validation"
            ) from None
        return ModelResult(output=output, run_id=row["id"], raw_path=raw_path)

    def _persist_prompt(self, prompt: str) -> tuple[str, str]:
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        relative = f"raw/prompts/{digest}.md"
        try:
            self.paths.write_immutable(relative, prompt)
        except FileExistsError:
            if self.paths.read(relative) != prompt:
                raise GatewayCacheError("Stored prompt does not match its content hash") from None
        return digest, relative

    def _validate_pricing(self) -> None:
        if self.config.limits.daily_budget_usd is None:
            return
        if any(
            model.input_usd_per_million is None or model.output_usd_per_million is None
            for model in self.config.models.values()
        ):
            raise GatewayBudgetError("Daily budget requires input and output prices for all models")

    def _reserve_attempt(
        self,
        *,
        run_id: str,
        role: str,
        action_key: str,
        model_config: ModelConfig,
        prompt: str,
        input_text: str,
        output_schema_json: str,
        prompt_hash: str,
        prompt_path: str,
        trace_id: str,
        metadata: dict[str, str],
    ) -> float:
        reservation = _worst_case_cost(
            prompt, input_text, output_schema_json, model_config, self.config
        )
        scope_type, scope_id = _scope(metadata)
        with self.db.transaction() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM model_runs WHERE project_id=1"
            ).fetchone()[0]
            if count >= self.config.limits.max_model_runs:
                raise GatewayLimitError("Project model run limit reached")

            daily_budget = self.config.limits.daily_budget_usd
            if daily_budget is not None:
                spent = connection.execute(
                    "SELECT COALESCE(SUM(COALESCE(estimated_cost_usd,0) + "
                    "COALESCE(reserved_cost_usd,0)),0) FROM model_runs "
                    "WHERE project_id=1 AND started_at >= datetime('now','start of day')"
                ).fetchone()[0]
                if float(spent) + reservation > float(daily_budget):
                    raise GatewayBudgetError("Daily estimated model budget would be exceeded")

            connection.execute(
                "INSERT INTO model_runs("
                "id,project_id,agent_role,scope_type,scope_id,action_key,model_name,"
                "reasoning_effort,prompt_hash,prompt_path,reserved_cost_usd,trace_id,status,"
                "metadata_json) VALUES(?,1,?,?,?,?,?,?,?,?,?,?, 'RUNNING',?)",
                (
                    run_id,
                    role,
                    scope_type,
                    scope_id,
                    action_key,
                    model_config.name,
                    model_config.reasoning_effort,
                    prompt_hash,
                    prompt_path,
                    reservation,
                    trace_id,
                    json.dumps(metadata, sort_keys=True),
                ),
            )
        return reservation

    def _record_failure(
        self,
        run_id: str,
        exc: Exception,
        *,
        reservation: float,
        invocation: _Invocation | None,
        model_config: ModelConfig,
    ) -> None:
        input_tokens = invocation.input_tokens if invocation else None
        output_tokens = invocation.output_tokens if invocation else None
        total_tokens = invocation.total_tokens if invocation else None
        cost = _actual_cost(invocation, model_config) if invocation else None
        self.db.execute(
            "UPDATE model_runs SET status='FAILED',completed_at=CURRENT_TIMESTAMP,error=?,"
            "input_tokens=?,output_tokens=?,total_tokens=?,estimated_cost_usd=?,"
            "reserved_cost_usd=? WHERE id=?",
            (
                _safe_error(exc),
                input_tokens,
                output_tokens,
                total_tokens,
                cost,
                0.0 if cost is not None else reservation,
                run_id,
            ),
        )


class OpenAIModelGateway(_PersistentGateway):
    async def _invoke(
        self,
        *,
        role: str,
        input_text: str,
        output_type: type[T],
        action_key: str,
        prompt: str,
        model_config: ModelConfig,
        trace_id: str,
        metadata: dict[str, str],
    ) -> _Invocation:
        del action_key
        tools = [WebSearchTool()] if ROLE_DESCRIPTORS[role].supports_web_search else []
        agent = Agent(
            name=role,
            instructions=prompt,
            output_type=output_type,
            model=model_config.name,
            model_settings=ModelSettings(
                reasoning={"effort": model_config.reasoning_effort},
                verbosity=model_config.verbosity,
                max_tokens=self.config.limits.max_output_tokens,
            ),
            tools=tools,
        )
        trace_metadata = _safe_invocation_metadata(self.db.project["slug"], role, metadata)
        result = await Runner.run(
            agent,
            input_text,
            # Every model turn needs its own application reservation and audit row.
            # A missing final response is retried by the gateway, never inside Runner.
            max_turns=1,
            run_config=RunConfig(
                workflow_name="Math research agent",
                trace_id=trace_id,
                group_id=_trace_group(metadata),
                trace_metadata=trace_metadata,
                tracing_disabled=not self.config.tracing.enabled,
                trace_include_sensitive_data=False,
            ),
        )
        usage = result.context_wrapper.usage
        return _Invocation(
            output=result.final_output,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )


class FakeModelGateway(_PersistentGateway):
    def __init__(
        self,
        db: Database,
        paths: Paths,
        config: Config,
        script: dict[str, list[Any]] | None = None,
    ) -> None:
        super().__init__(db, paths, config)
        self._script = {key: list(values) for key, values in (script or {}).items()}

    async def _invoke(
        self,
        *,
        role: str,
        input_text: str,
        output_type: type[T],
        action_key: str,
        prompt: str,
        model_config: ModelConfig,
        trace_id: str,
        metadata: dict[str, str],
    ) -> _Invocation:
        del output_type, prompt, model_config, trace_id
        values = self._script.get(action_key)
        if values is None:
            values = self._script.get(role)
        if values is not None:
            if not values:
                raise GatewayInvocationError("Fake gateway script is exhausted")
            value = values.pop(0)
        elif role == "editor":
            try:
                raw_content = json.loads(input_text)["raw_content"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise GatewayInvocationError(
                    "Default fake editor requires raw_content JSON"
                ) from exc
            value = EditorOutput(
                edited_content=str(raw_content).replace("REDUNDANT ", ""),
                consistency_issues=[],
            )
        else:
            raise GatewayInvocationError(f"No fake gateway script for action {action_key}")

        if isinstance(value, BaseException):
            raise value
        if callable(value):
            value = value(input_text, metadata)
            if inspect.isawaitable(value):
                value = await value
        return _Invocation(output=value)


def _load_prompt(filename: str) -> str:
    try:
        packaged = resources.files("math_research_agent").joinpath("prompts", filename)
        return packaged.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        source = Path(__file__).resolve().parents[2] / "prompts" / filename
        try:
            return source.read_text(encoding="utf-8")
        except OSError as exc:
            raise GatewayError(f"Role prompt is unavailable: {filename}") from exc


def _scope(metadata: dict[str, str]) -> tuple[str | None, str | None]:
    if metadata.get("scope_type") and metadata.get("scope_id"):
        return metadata["scope_type"], metadata["scope_id"]
    for metadata_key, scope_type in (
        ("branch", "branch"),
        ("branch_id", "branch"),
        ("probe", "probe"),
        ("probe_id", "probe"),
        ("cycle", "brain_cycle"),
        ("brain_cycle_id", "brain_cycle"),
        ("cycle_id", "brain_cycle"),
    ):
        if metadata.get(metadata_key):
            return scope_type, metadata[metadata_key]
    return None, None


def _trace_group(metadata: dict[str, str]) -> str | None:
    for key in ("branch", "branch_id", "cycle", "brain_cycle_id", "cycle_id"):
        if metadata.get(key):
            return metadata[key]
    return None


def _safe_invocation_metadata(
    project_slug: str, role: str, metadata: dict[str, str]
) -> dict[str, str]:
    result = {
        "project": metadata.get("project", str(project_slug)),
        "role": role,
    }
    aliases = {
        "cycle": ("cycle", "brain_cycle_id", "cycle_id"),
        "branch": ("branch", "branch_id"),
        "probe": ("probe", "probe_id"),
        "job": ("job", "job_id"),
    }
    for name, keys in aliases.items():
        value = next((metadata[key] for key in keys if metadata.get(key)), None)
        if value is not None:
            result[name] = value
    return result


def _log_invocation(project_slug: str, role: str, metadata: dict[str, str]) -> None:
    values = _safe_invocation_metadata(project_slug, role, metadata)
    logger.info(
        "Model invocation project=%s role=%s cycle=%s branch=%s probe=%s job=%s",
        values["project"],
        values["role"],
        values.get("cycle", "-"),
        values.get("branch", "-"),
        values.get("probe", "-"),
        values.get("job", "-"),
    )


def _output_schema_json(output_type: type[Any]) -> str:
    schema = AgentOutputSchema(output_type)
    if schema.is_plain_text():
        return ""
    return json.dumps(
        {
            "type": "json_schema",
            "name": schema.name(),
            "schema": schema.json_schema(),
            "strict": schema.is_strict_json_schema(),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _worst_case_cost(
    prompt: str,
    input_text: str,
    output_schema_json: str,
    model: ModelConfig,
    config: Config,
) -> float:
    if config.limits.daily_budget_usd is None:
        return 0.0
    assert model.input_usd_per_million is not None
    assert model.output_usd_per_million is not None
    conservative_input_tokens = (
        len(prompt.encode("utf-8"))
        + len(input_text.encode("utf-8"))
        + len(output_schema_json.encode("utf-8"))
    )
    return (
        conservative_input_tokens * float(model.input_usd_per_million)
        + config.limits.max_output_tokens * float(model.output_usd_per_million)
    ) / 1_000_000


def _actual_cost(invocation: _Invocation | None, model: ModelConfig) -> float | None:
    if (
        invocation is None
        or invocation.input_tokens is None
        or invocation.output_tokens is None
        or model.input_usd_per_million is None
        or model.output_usd_per_million is None
    ):
        return None
    return (
        invocation.input_tokens * float(model.input_usd_per_million)
        + invocation.output_tokens * float(model.output_usd_per_million)
    ) / 1_000_000


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, asyncio.TimeoutError):
        return "Model invocation timed out"
    if isinstance(exc, ValidationError):
        return "Structured output validation failed"
    return f"Model invocation failed ({type(exc).__name__})"
