"""Small local runtime configuration; no API credentials or model fallback."""

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    manual_review_enabled: bool = False
    # Keep the saved v0.2 key; the newer name describes an upper limit, not a target.
    target_active_leaves: int = Field(
        default=8,
        ge=1,
        le=256,
        validation_alias=AliasChoices("target_active_leaves", "max_active_leaves"),
    )
    max_concurrent_pro_turns: int = Field(default=4, ge=1, le=64)
    format_retries: int = Field(default=2, ge=0, le=3)
    transport: Literal["manual", "fake", "bridge"] = "manual"
    bridge_base_url: str = "http://127.0.0.1:8080"
    bridge_request_timeout: float = Field(default=20, gt=0)
    bridge_turn_timeout: float = Field(default=1800, gt=0)
    bridge_pro_model: str = "GPT-6 Pro"
    bridge_parent_model: str = "GPT-6 Thinking"
    bridge_parent_effort: str = "xhigh"
    projects_root: Path = Path("projects")

    @property
    def max_active_leaves(self) -> int:
        return self.target_active_leaves


def load_config(path: Path | None = None, **kwargs) -> Config:
    path = path or kwargs.get("global_path")
    values = yaml.safe_load(path.read_text()) if path else {}
    values = values or {}
    if os.getenv("MATHAGENT_PROJECTS_ROOT"):
        values["projects_root"] = os.environ["MATHAGENT_PROJECTS_ROOT"]
    return Config.model_validate(values)
