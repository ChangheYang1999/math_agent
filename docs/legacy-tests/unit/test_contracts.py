from pathlib import Path

import pytest
from pydantic import ValidationError

from math_research_agent.agents import ROLE_DESCRIPTORS
from math_research_agent.config import Config, load_config
from math_research_agent.models import (
    BrainCycleStatus,
    BranchStatus,
    JobStatus,
    ProbeStatus,
    can_transition,
    is_legal_branch_transition,
    is_legal_probe_transition,
)
from math_research_agent.schemas import (
    ArtifactDraft,
    BranchProposal,
    EditorOutput,
    ProbeAssessment,
    ProbeFormulation,
    SolverOutput,
)


def artifact(kind: str = "report") -> ArtifactDraft:
    return ArtifactDraft(kind=kind, content="Mathematical content", editor_mode="aggressive")


def formulation() -> ProbeFormulation:
    return ProbeFormulation(
        mathematical_question="Is x^2 nonnegative for every real x?",
        proof_criterion="Derive x^2 >= 0 for arbitrary real x.",
        disproof_criterion="Exhibit a real x with x^2 < 0.",
        implication_if_proved="The proposed sign obstruction is absent.",
        implication_if_disproved="The sign based route fails.",
        relevance_to_parent_insight="Tests the needed sign condition.",
        artifact=artifact("probe"),
    )


def solver_payload(verdict: str) -> dict[str, object]:
    return {
        "verdict": verdict,
        "short_result": "Result",
        "strongest_established_statement": "Exact result",
        "artifact": artifact("solver_report"),
    }


def assessment_payload(verdict: str, action: str) -> dict[str, object]:
    return {
        "solver_verdict": verdict,
        "action": action,
        "interpretation": "Local interpretation",
        "parent_insight_effect": "Local evidence",
        "artifact": artifact("assessment"),
    }


def test_config_defaults_cover_every_role_and_hard_limit() -> None:
    config = Config()

    assert set(config.models) == {"background", "brain", "probe_manager", "solver", "editor"}
    assert config.limits.max_active_branches == 8
    assert config.limits.max_concurrent_branches == 4
    assert config.limits.max_probe_rounds == 3
    assert config.limits.max_new_branches_per_brain_cycle == 6
    assert config.limits.max_model_attempts == 3
    assert config.limits.max_pdf_mb == 50
    assert config.limits.daily_budget_usd is None
    assert config.limits.max_model_runs == 10_000
    assert config.limits.max_output_tokens == 16_000
    assert config.limits.max_context_chars == 160_000
    assert config.runtime.timeout_seconds == 300
    assert config.runtime.retry_base_seconds == 1
    assert config.runtime.lease_seconds == 900
    assert config.editor.fail_closed is True
    assert config.literature.download_open_access_pdfs is True
    assert config.tracing.enabled is True
    assert config.projects_root == Path("projects")


def test_load_config_deep_merges_global_project_and_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    global_path = tmp_path / "global.yaml"
    project_path = tmp_path / "project.yaml"
    global_path.write_text(
        "limits:\n  max_probe_rounds: 5\nmodels:\n  solver:\n    name: global-solver\n",
        encoding="utf-8",
    )
    project_path.write_text(
        "limits:\n  max_active_branches: 2\nmodels:\n  solver:\n    reasoning_effort: low\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MATHAGENT_PROJECTS_ROOT", "/tmp/research-projects")
    monkeypatch.setenv("MATHAGENT_MODEL_SOLVER", "environment-solver")

    config = load_config(global_path, project_path)

    assert config.limits.max_probe_rounds == 5
    assert config.limits.max_active_branches == 2
    assert config.limits.max_concurrent_branches == 4
    assert config.models["solver"].name == "environment-solver"
    assert config.models["solver"].reasoning_effort == "low"
    assert config.projects_root == Path("/tmp/research-projects")


@pytest.mark.parametrize("field", ["max_probe_rounds", "max_model_runs", "max_output_tokens"])
def test_config_rejects_nonpositive_hard_limits(field: str) -> None:
    with pytest.raises(ValidationError):
        Config(limits={field: 0})


def test_branch_proposal_requires_exactly_one_resolvable_parent() -> None:
    existing = BranchProposal(
        parent_insight_id="I-000004",
        objective="Test a sign condition",
        why_now="It is decisive",
        priority="high",
        decisive_question_hint="Does the sign condition hold?",
    )
    new = BranchProposal(
        new_insight_index=0,
        objective="Test a scaling condition",
        why_now="It is cheap",
        priority="medium",
        decisive_question_hint="Is the exponent critical?",
    )

    assert existing.parent_insight_id == "I-000004"
    assert new.new_insight_index == 0
    for invalid in ({}, {"parent_insight_id": "I-1", "new_insight_index": 0}):
        with pytest.raises(ValidationError):
            BranchProposal(
                **invalid,
                objective="Objective",
                why_now="Reason",
                priority="low",
                decisive_question_hint="Question",
            )
    with pytest.raises(ValidationError):
        BranchProposal(
            new_insight_index=-1,
            objective="Objective",
            why_now="Reason",
            priority="low",
            decisive_question_hint="Question",
        )


@pytest.mark.parametrize("verdict", ["PROVED", "DISPROVED"])
def test_conclusive_solver_output_requires_proof_or_counterexample(verdict: str) -> None:
    with pytest.raises(ValidationError):
        SolverOutput(**solver_payload(verdict))

    payload = solver_payload(verdict)
    payload["proof_or_counterexample"] = "A complete rigorous argument."
    assert SolverOutput(**payload).verdict == verdict


def test_inconclusive_solver_output_requires_precise_bottleneck() -> None:
    with pytest.raises(ValidationError):
        SolverOutput(**solver_payload("INCONCLUSIVE"))

    payload = solver_payload("INCONCLUSIVE")
    payload["bottleneck"] = "The endpoint estimate is unavailable."
    assert SolverOutput(**payload).bottleneck == "The endpoint estimate is unavailable."


def test_probe_assessment_enforces_action_constraints() -> None:
    reformulate = assessment_payload("INCONCLUSIVE", "REFORMULATE")
    with pytest.raises(ValidationError):
        ProbeAssessment(**reformulate)
    reformulate["next_probe"] = formulation()
    assert ProbeAssessment(**reformulate).next_probe is not None

    terminal = assessment_payload("INCONCLUSIVE", "TOO_HARD")
    terminal["next_probe"] = formulation()
    with pytest.raises(ValidationError):
        ProbeAssessment(**terminal)

    with pytest.raises(ValidationError):
        ProbeAssessment(**assessment_payload("DISPROVED", "CONFIRM"))
    with pytest.raises(ValidationError):
        ProbeAssessment(**assessment_payload("PROVED", "REFUTE"))


def test_schema_models_forbid_unstructured_control_fields_and_default_lists() -> None:
    inconclusive = solver_payload("INCONCLUSIVE")
    inconclusive["bottleneck"] = "Missing lemma"
    output = SolverOutput(**inconclusive)

    assert output.exact_assumptions_used == []
    assert output.discovered_obstructions == []
    assert EditorOutput(edited_content="short").consistency_issues == []
    with pytest.raises(ValidationError):
        ProbeAssessment(**assessment_payload("PROVED", "CONFIRM"), branch_status="CONFIRMED")
    with pytest.raises(ValidationError):
        ArtifactDraft(kind="x", content="y", editor_mode="aggressive", path="/tmp/model-path")


def test_state_transitions_are_explicit_and_terminal_states_cannot_restart() -> None:
    assert is_legal_branch_transition(BranchStatus.QUEUED, BranchStatus.RUNNING)
    assert is_legal_branch_transition(BranchStatus.RUNNING, BranchStatus.WAITING_FOR_SOLVER)
    assert is_legal_branch_transition(
        BranchStatus.WAITING_FOR_SOLVER, BranchStatus.WAITING_FOR_MANAGER
    )
    assert is_legal_branch_transition(BranchStatus.WAITING_FOR_MANAGER, BranchStatus.CONFIRMED)
    assert not is_legal_branch_transition(BranchStatus.CONFIRMED, BranchStatus.RUNNING)
    assert is_legal_probe_transition(ProbeStatus.DRAFTED, ProbeStatus.EDITED)
    assert not is_legal_probe_transition(ProbeStatus.ASSESSED, ProbeStatus.SOLVING)


def test_generic_transition_check_dispatches_by_state_type() -> None:
    assert can_transition(BrainCycleStatus.PENDING, BrainCycleStatus.RUNNING)
    assert can_transition(JobStatus.RUNNING, JobStatus.COMPLETED)
    assert not can_transition(JobStatus.COMPLETED, JobStatus.RUNNING)
    assert not can_transition(BranchStatus.QUEUED, ProbeStatus.EDITED)


def test_agent_role_descriptors_bind_prompts_and_typed_outputs() -> None:
    assert set(ROLE_DESCRIPTORS) == {"background", "brain", "probe_manager", "solver", "editor"}
    for role, descriptor in ROLE_DESCRIPTORS.items():
        assert descriptor.name == role
        assert descriptor.prompt_filename == f"{role}.md"
        assert descriptor.output_schema is not None
    assert ROLE_DESCRIPTORS["background"].supports_web_search is True
    assert all(
        not descriptor.supports_web_search
        for role, descriptor in ROLE_DESCRIPTORS.items()
        if role != "background"
    )


def test_probe_declares_inconclusive_consequence_before_solving():
    from math_research_agent.schemas import ProbeFormulation

    probe = ProbeFormulation(
        mathematical_question="Does the inequality hold?",
        proof_criterion="A proof",
        disproof_criterion="A counterexample",
        implication_if_proved="Supports route",
        implication_if_disproved="Rejects route",
        implication_if_inconclusive="Test a finite-dimensional reduction before spending more.",
        relevance_to_parent_insight="Necessary condition",
        artifact={"kind": "probe", "editor_mode": "prompt", "content": "Precise local claim"},
    )
    assert (
        probe.implication_if_inconclusive
        == "Test a finite-dimensional reduction before spending more."
    )
