"""Validated research contracts. These are gates, not suggestions to the model."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PRO_MODEL = "GPT-6 Pro"
PARENT_MODEL = "GPT-6 Extra High"


def require_english(value: str) -> str:
    # A deliberately lightweight guard, not a general language detector.
    if re.search(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]", value):
        raise ValueError("ENGLISH_ONLY: translate user-boundary text before research")
    return value


def concrete_prompt(value: str) -> str:
    require_english(value)
    if len(value.strip()) < 60 or len(value.split()) < 9:
        raise ValueError(
            "A complete specific next prompt is required (at least 60 characters and 9 words)"
        )
    if value.strip().lower().rstrip(".!") in {"continue working", "continue", "keep working"}:
        raise ValueError("A generic continuation is not a concrete task")
    return value.strip()


class ResearchContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def english_artifact(self):
        def check(value):
            if isinstance(value, str):
                require_english(value)
            elif isinstance(value, dict):
                for item in value.values():
                    check(item)
            elif isinstance(value, list):
                for item in value:
                    check(item)

        check(self.model_dump())
        return self


class ResearchNode(ResearchContract):
    id: Text
    parent_id: str | None = None
    goal: Text
    relative_weight: float = Field(default=1, ge=0, le=1)
    status: Literal["ACTIVE", "PAUSED", "COMPLETED", "ABANDONED"] = "ACTIVE"
    research_state: str = ""
    conversation_id: str | None = None
    round_counter: int = 0


class LeafRoundReport(ResearchContract):
    node_id: Text
    round_id: Text
    status: Literal["SOLVED", "PARTIAL", "STUCK"]
    summary: Text
    findings: list[str]
    evidence: Text
    obstacles: list[str]
    recommended_next_steps: list[str]
    split_suggestion: list[str] = Field(default_factory=list)
    important_update: bool = False


class ChildTask(ResearchContract):
    goal: Text
    relative_weight: float = Field(gt=0, le=1)
    initial_prompt: Text

    _prompt = field_validator("initial_prompt")(concrete_prompt)


class TreeAction(ResearchContract):
    type: Literal["split", "reweight", "pause", "resume", "complete", "abandon"]
    node_id: Text
    children: list[ChildTask] = Field(default_factory=list)
    weights: dict[str, float] = Field(default_factory=dict)


class InternalMessage(ResearchContract):
    sender_node_id: Text
    recipient_node_id: Text
    message: Text
    evidence_reference: Text
    reason: Text


class ReportUpdate(ResearchContract):
    node_id: Text
    body: Text
    claim_status: Literal["MODEL_PROPOSED", "CONJECTURAL", "NUMERICAL", "VERIFIED"]
    significant: bool
    evidence_reference: Text
    independent_verification: str = ""


class ParentRoundResponse(ResearchContract):
    child_node_id: Text
    responding_to_round_id: Text
    assessment: Text
    next_prompt: Text
    proposed_tree_actions: list[TreeAction] = Field(default_factory=list)
    proposed_messages: list[InternalMessage] = Field(default_factory=list)
    proposed_report_updates: list[ReportUpdate] = Field(default_factory=list)

    _prompt = field_validator("next_prompt")(concrete_prompt)


class ParentDiscussionResponse(ResearchContract):
    reply: Text


class UserDisplayTranslation(BaseModel):
    """Human-boundary text only; never inserted into research state or prompts."""

    model_config = ConfigDict(extra="forbid")
    display_text: Text


class BootstrapResponse(ResearchContract):
    children: list[ChildTask] = Field(min_length=1)
    research_state: str = ""

    @model_validator(mode="after")
    def conserved(self):
        if abs(sum(c.relative_weight for c in self.children) - 1) > 1e-8:
            raise ValueError("Child relative weights must sum to one")
        if len({c.goal.lower() for c in self.children}) != len(self.children):
            raise ValueError("Child tasks must have distinct goals")
        return self


class CoordinationResponse(ResearchContract):
    research_state: str
    proposed_tree_actions: list[TreeAction] = Field(default_factory=list)
    proposed_messages: list[InternalMessage] = Field(default_factory=list)
    proposed_report_updates: list[ReportUpdate] = Field(default_factory=list)


class TranslationResponse(ResearchContract):
    english_text: Text
