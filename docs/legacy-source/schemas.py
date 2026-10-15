"""Structured model outputs. Workflow control is never inferred from prose."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EditorMode = Literal["aggressive", "proof_safe", "prompt"]
Priority = Literal["low", "medium", "high"]
Confidence = Literal["low", "medium", "high"]
SolverVerdictValue = Literal["PROVED", "DISPROVED", "INCONCLUSIVE"]
AssessmentAction = Literal["CONFIRM", "REFUTE", "PARTIAL", "REFORMULATE", "TOO_HARD", "ABANDON"]


class StructuredOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArtifactDraft(StructuredOutput):
    kind: str
    content: str
    editor_mode: EditorMode


class LiteratureReference(StructuredOutput):
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    arxiv_id: str | None = None
    doi: str | None = None
    url: str | None = None
    pdf_url: str | None = None
    relevance: str
    key_results: list[str] = Field(default_factory=list)
    theorem_locations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class BackgroundOutput(StructuredOutput):
    normalized_problem_title: str
    literature: list[LiteratureReference] = Field(default_factory=list)
    problem_spec: ArtifactDraft
    literature_index: ArtifactDraft
    background_report: ArtifactDraft
    agent_context: ArtifactDraft
    references_bib: str | None = None


class InsightProposal(StructuredOutput):
    summary: str
    confidence: Confidence | None = None
    evidence_for: list[str] = Field(default_factory=list)
    evidence_against: list[str] = Field(default_factory=list)
    strategic_consequence: str
    priority: Priority


class InsightUpdate(StructuredOutput):
    insight_id: str
    new_status: Literal["ACTIVE", "STRENGTHENED", "WEAKENED", "REFUTED", "SUPERSEDED", "ARCHIVED"]
    reason: str


class BranchProposal(StructuredOutput):
    parent_insight_id: str | None = None
    new_insight_index: int | None = None
    objective: str
    why_now: str
    priority: Priority
    decisive_question_hint: str

    @model_validator(mode="after")
    def require_exactly_one_parent_reference(self) -> BranchProposal:
        references = (self.parent_insight_id is not None, self.new_insight_index is not None)
        if sum(references) != 1:
            raise ValueError("exactly one of parent_insight_id or new_insight_index is required")
        if self.new_insight_index is not None and self.new_insight_index < 0:
            raise ValueError("new_insight_index must be zero or greater")
        return self


class BrainOutput(StructuredOutput):
    global_assessment: str
    proof_vs_disproof_assessment: str
    new_insights: list[InsightProposal] = Field(default_factory=list)
    insight_updates: list[InsightUpdate] = Field(default_factory=list)
    branch_proposals: list[BranchProposal] = Field(default_factory=list)
    strategy_artifact: ArtifactDraft
    direction_tree_artifact: ArtifactDraft
    insight_log_appendix: ArtifactDraft
    decision_log_appendix: ArtifactDraft
    open_questions_artifact: ArtifactDraft


class ProbeFormulation(StructuredOutput):
    mathematical_question: str
    assumptions: list[str] = Field(default_factory=list)
    forbidden_assumptions: list[str] = Field(default_factory=list)
    proof_criterion: str
    disproof_criterion: str
    implication_if_proved: str
    implication_if_disproved: str
    implication_if_inconclusive: str = (
        "No confirmation or refutation; assess the bottleneck and tractability."
    )
    relevance_to_parent_insight: str
    artifact: ArtifactDraft


class SolverOutput(StructuredOutput):
    verdict: SolverVerdictValue
    short_result: str
    exact_assumptions_used: list[str] = Field(default_factory=list)
    strongest_established_statement: str
    proof_or_counterexample: str | None = None
    bottleneck: str | None = None
    discovered_obstructions: list[str] = Field(default_factory=list)
    artifact: ArtifactDraft

    @model_validator(mode="after")
    def require_verdict_evidence(self) -> SolverOutput:
        proof = (self.proof_or_counterexample or "").strip()
        bottleneck = (self.bottleneck or "").strip()
        if self.verdict in {"PROVED", "DISPROVED"} and not proof:
            raise ValueError(f"{self.verdict} requires proof_or_counterexample")
        if self.verdict == "INCONCLUSIVE" and not bottleneck:
            raise ValueError("INCONCLUSIVE requires a precise bottleneck")
        return self


class ProbeAssessment(StructuredOutput):
    solver_verdict: SolverVerdictValue
    action: AssessmentAction
    interpretation: str
    parent_insight_effect: str
    next_probe: ProbeFormulation | None = None
    artifact: ArtifactDraft

    @model_validator(mode="after")
    def validate_action(self) -> ProbeAssessment:
        if self.action == "REFORMULATE":
            if self.next_probe is None:
                raise ValueError("REFORMULATE requires next_probe")
        elif self.next_probe is not None:
            raise ValueError("terminal assessment actions must not include next_probe")
        if self.action == "CONFIRM" and self.solver_verdict != "PROVED":
            raise ValueError("CONFIRM requires a PROVED solver verdict")
        if self.action == "REFUTE" and self.solver_verdict != "DISPROVED":
            raise ValueError("REFUTE requires a DISPROVED solver verdict")
        return self


class EditorOutput(StructuredOutput):
    edited_content: str
    consistency_issues: list[str] = Field(default_factory=list)
