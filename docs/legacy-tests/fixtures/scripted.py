"""Small hand-checked mathematical fixtures; no external requests."""

import inspect
import json
from types import SimpleNamespace


def draft(content, mode="aggressive"):
    return dict(kind="text", editor_mode=mode, content=content)


def formulation(question="For real x, is x² nonnegative?"):
    return dict(
        mathematical_question=question,
        assumptions=["x is real"],
        forbidden_assumptions=["x > 0"],
        proof_criterion="Prove for every real x",
        disproof_criterion="Give one real counterexample",
        implication_if_proved="Supports positivity",
        implication_if_disproved="Refutes positivity",
        relevance_to_parent_insight="Tests a necessary sign condition",
        artifact=draft(question, "prompt"),
    )


def solver(verdict):
    return dict(
        verdict=verdict,
        short_result=verdict,
        exact_assumptions_used=["x is real"],
        strongest_established_statement="x² ≥ 0"
        if verdict == "PROVED"
        else "The tested claim fails",
        proof_or_counterexample=(
            "If x ≥ 0 its product with itself is nonnegative; if x < 0, x²=(-x)² ≥ 0."
            if verdict == "PROVED"
            else "x=-1 is a counterexample."
            if verdict == "DISPROVED"
            else None
        ),
        bottleneck="REDUNDANT Need a sign lemma." if verdict == "INCONCLUSIVE" else None,
        discovered_obstructions=[],
        artifact=draft("REDUNDANT Local mathematical result.", "proof_safe"),
    )


def assessment(verdict, action, next_probe=None):
    return dict(
        solver_verdict=verdict,
        action=action,
        interpretation="REDUNDANT Interprets only the local test.",
        parent_insight_effect="Update the sign route.",
        next_probe=next_probe,
        artifact=draft("Local assessment."),
    )


def brain_output(first=True):
    new = [
        dict(
            summary="Squares have a useful sign.",
            strategic_consequence="Test positivity",
            priority="high",
        ),
        dict(
            summary="Every real number may be positive.",
            strategic_consequence="Try a negative number",
            priority="high",
        ),
    ]
    branches = [
        dict(
            new_insight_index=i,
            objective=("Test x² ≥ 0" if i == 0 else "Test x ≥ 0"),
            why_now="Cheap decisive test",
            priority="high",
            decisive_question_hint="Use real numbers",
        )
        for i in range(2)
    ]
    updates = [
        dict(
            insight_id="I-000001",
            new_status="STRENGTHENED",
            reason="Square proof supports this route",
        ),
        dict(insight_id="I-000002", new_status="REFUTED", reason="Negative counterexample"),
    ]
    return dict(
        global_assessment="Two local sign tests.",
        proof_vs_disproof_assessment="Consider both outcomes.",
        new_insights=new if first else [],
        insight_updates=[] if first else updates,
        branch_proposals=branches if first else [],
        strategy_artifact=draft(
            "Test signs." if first else "Retain square positivity; reject positivity of all reals."
        ),
        direction_tree_artifact=draft("Sign tests"),
        insight_log_appendix=draft("Sign insights recorded"),
        decision_log_appendix=draft("Prioritize decisive tests"),
        open_questions_artifact=draft("Which PDE energy has this sign?"),
    )


def background_output():
    return dict(
        normalized_problem_title="Sign conditions",
        literature=[],
        problem_spec=draft("Study sign conditions on real quantities."),
        literature_index=draft("[PROVED] Real squares are nonnegative."),
        background_report=draft(
            "[OPEN] Determine the useful energy quantity; this simulation has no literature search."
        ),
        agent_context=draft("Real x. Do not assume x > 0. Gap G1: identify sign-definite energy."),
        references_bib=None,
    )


class ScriptGateway:
    """Network boundary double with persistent action replay for branch recovery tests."""

    def __init__(self, script=None):
        self.script = script or {}
        self.cache = {}
        self.inputs = []

    async def run_structured(self, **kw):
        key = kw["action_key"]
        if key in self.cache:
            return self.cache[key]
        self.inputs.append(kw)
        if kw["role"] == "editor":
            payload = json.loads(kw["input_text"])
            value = dict(
                edited_content=payload["raw_content"].replace("REDUNDANT ", ""),
                consistency_issues=[],
            )
            if self.script.get("editor"):
                value = self.script["editor"].pop(0)
        else:
            values = self.script.get(key, self.script.get(kw["role"]))
            if not values:
                raise AssertionError(f"No scripted result for {key}")
            value = values.pop(0)
        if isinstance(value, Exception):
            raise value
        if callable(value):
            value = value(kw)
            if inspect.isawaitable(value):
                value = await value
        output = kw["output_type"].model_validate(value)
        result = SimpleNamespace(output=output, run_id=key, raw_path="raw/test-output.json")
        self.cache[key] = result
        return result
