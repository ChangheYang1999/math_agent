"""Typed configuration and deterministic override loading."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, NonNegativeFloat, PositiveInt, model_validator

RoleName = Literal["background", "brain", "probe_manager", "solver", "editor"]
ROLE_NAMES: tuple[RoleName, ...] = (
    "background",
    "brain",
    "probe_manager",
    "solver",
    "editor",
)


class StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelConfig(StrictConfigModel):
    name: str
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] = "high"
    verbosity: Literal["low", "medium", "high"] = "low"
    input_usd_per_million: NonNegativeFloat | None = None
    output_usd_per_million: NonNegativeFloat | None = None


def _default_models() -> dict[str, ModelConfig]:
    return {
        "background": ModelConfig(name="gpt-5.6-sol", reasoning_effort="high"),
        "brain": ModelConfig(name="gpt-5.6-sol", reasoning_effort="high"),
        "probe_manager": ModelConfig(name="gpt-5.6-sol", reasoning_effort="medium"),
        "solver": ModelConfig(name="gpt-5.6-sol", reasoning_effort="high"),
        "editor": ModelConfig(name="gpt-5.6-luna", reasoning_effort="medium"),
    }


class LimitsConfig(StrictConfigModel):
    max_active_branches: PositiveInt = 8
    max_concurrent_branches: PositiveInt = 4
    max_probe_rounds: PositiveInt = 3
    max_new_branches_per_brain_cycle: PositiveInt = 6
    max_model_attempts: PositiveInt = 3
    max_pdf_mb: PositiveInt = 50
    daily_budget_usd: NonNegativeFloat | None = None
    max_model_runs: PositiveInt = 10_000
    max_output_tokens: PositiveInt = 16_000
    max_context_chars: PositiveInt = 160_000


class EditorConfig(StrictConfigModel):
    fail_closed: bool = True


class LiteratureConfig(StrictConfigModel):
    download_open_access_pdfs: bool = True


class TracingConfig(StrictConfigModel):
    enabled: bool = True


class RuntimeConfig(StrictConfigModel):
    timeout_seconds: PositiveInt = 300
    retry_base_seconds: NonNegativeFloat = 1
    lease_seconds: PositiveInt = 900


class Config(StrictConfigModel):
    models: dict[str, ModelConfig] = Field(default_factory=_default_models)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    editor: EditorConfig = Field(default_factory=EditorConfig)
    literature: LiteratureConfig = Field(default_factory=LiteratureConfig)
    tracing: TracingConfig = Field(default_factory=TracingConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    projects_root: Path = Path("projects")

    @model_validator(mode="after")
    def require_model_roles(self) -> Config:
        missing = set(ROLE_NAMES).difference(self.models)
        unknown = set(self.models).difference(ROLE_NAMES)
        if missing or unknown:
            details = []
            if missing:
                details.append(f"missing roles: {', '.join(sorted(missing))}")
            if unknown:
                details.append(f"unknown roles: {', '.join(sorted(unknown))}")
            raise ValueError(
                "models must define exactly the supported roles (" + "; ".join(details) + ")"
            )
        return self


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read configuration file {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML in configuration file {path}: {exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"configuration file {path} must contain a YAML mapping")
    return loaded


def load_config(global_path: Path | None = None, project_path: Path | None = None) -> Config:
    """Load defaults, then global YAML, project YAML, and supported environment overrides."""

    values = Config().model_dump(mode="python")
    for path in (global_path, project_path):
        if path is not None:
            values = _deep_merge(values, _read_yaml(Path(path)))

    projects_root = os.getenv("MATHAGENT_PROJECTS_ROOT")
    if projects_root:
        values["projects_root"] = projects_root
    for role in ROLE_NAMES:
        model_name = os.getenv(f"MATHAGENT_MODEL_{role.upper()}")
        if model_name:
            values["models"][role]["name"] = model_name
    return Config.model_validate(values)
