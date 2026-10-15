"""Focused parent payload preservation, restoration and immutable-turn checks."""

import json

from math_research_agent.config import Config
from math_research_agent.scheduler import Scheduler
from math_research_agent.schemas import PARENT_MODEL, PRO_MODEL, ParentRoundResponse
from math_research_agent.store import Store
from math_research_agent.transport import ScriptedTransport

TASK = "Prove the odd-number sum identity rigorously, checking every induction hypothesis and the base case before returning a structured report."


async def pending_second_report(tmp_path):
    store = Store.initialize(
        tmp_path, "Prove the sum of positive odd integers.", Config(transport="fake")
    )
    child = store.split(
        "root",
        [{"goal": "Prove the odd-number identity.", "relative_weight": 1, "initial_prompt": TASK}],
    )[0]

    def report(context):
        number = context["round_id"].rsplit("r", 1)[-1]
        evidence = ("PRIOR_PROOF: " if number == "000001" else "CURRENT_PROOF: ") + (
            "For n>=1, S_(n+1)=n^2+2n+1=(n+1)^2.\\n" * 300
        )
        return {
            "node_id": child,
            "round_id": context["round_id"],
            "status": "SOLVED",
            "summary": "The induction step and base case establish the identity.",
            "findings": ["The stated positive-integer hypotheses suffice."],
            "evidence": evidence,
            "obstacles": [],
            "recommended_next_steps": [],
        }

    transport = ScriptedTransport(store, {"leaf": report})
    scheduler = Scheduler(store, transport)
    first = store.one("SELECT id FROM rounds WHERE node_id=?", (child,))["id"]
    await scheduler._leaf(first)
    await scheduler._parent(first)
    second = store.one("SELECT id FROM rounds WHERE previous_round_id=?", (first,))["id"]
    await scheduler._leaf(second)
    state = json.loads(store.node("root")["research_state"])
    state["essential_hypothesis"] = (
        "All variables are integers with n>=1; no convergence assumption."
    )
    store.execute("UPDATE nodes SET research_state=? WHERE id='root'", (json.dumps(state),))
    return store, transport, scheduler, first, second


async def test_warm_parent_omits_prior_proof_but_keeps_complete_current_report_and_contract(
    tmp_path,
):
    store, transport, scheduler, first, second = await pending_second_report(tmp_path)
    current = json.loads(store.one("SELECT report FROM rounds WHERE id=?", (second,))["report"])
    await scheduler._parent(second)
    call = transport.calls[-1]
    context = call["context"]
    assert context["report"] == current
    assert len(context["report"]["evidence"]) > 10_000
    assert "PRIOR_PROOF" not in call["prompt"] and "restored_history" not in context
    assert context["prior_report_references"][0]["round_id"] == first
    assert "child_assessments" not in context["research_state"]
    assert "n>=1" in context["research_state"]["essential_hypothesis"]
    assert context["model_roles"]["parent"] == PARENT_MODEL
    assert context["model_roles"]["child"] == PRO_MODEL
    assert context["review"] == {"manual_review_enabled": False, "current_report_accepted": True}
    schema = json.loads(call["prompt"].split("\nOUTPUT_SCHEMA_JSON\n")[1])
    assert schema["required"] == ParentRoundResponse.model_json_schema()["required"]
    assert schema["additionalProperties"] is False
    assert set(schema["$defs"]["TreeAction"]["properties"]["type"]["enum"]) == {
        "split",
        "reweight",
        "pause",
        "resume",
        "complete",
        "abandon",
    }
    assert schema["$defs"]["ChildTask"]["properties"]["relative_weight"]["exclusiveMinimum"] == 0


async def test_replaced_parent_restores_full_prior_proof_and_validated_decision(tmp_path):
    store, transport, scheduler, first, second = await pending_second_report(tmp_path)
    old_session = store.one("SELECT id FROM sessions WHERE node_id='root' AND active=1")["id"]
    replacement = await transport.rollover_session(old_session, "new-parent-conversation")
    await scheduler._parent(second)
    call = transport.calls[-1]
    assert call["session_id"] == replacement.id != old_session
    history = call["context"]["restored_history"]
    assert history[0]["report"] == json.loads(
        store.one("SELECT report FROM rounds WHERE id=?", (first,))["report"]
    )
    assert len(history[0]["report"]["evidence"]) > 10_000
    assert history[0]["parent_response"] == json.loads(
        store.one("SELECT payload FROM parent_responses WHERE round_id=?", (first,))["payload"]
    )
    assert "CURRENT_PROOF" in call["context"]["report"]["evidence"]


async def test_existing_queued_parent_prompt_is_not_rewritten_by_new_assembly(tmp_path):
    store, transport, scheduler, first, second = await pending_second_report(tmp_path)
    report = json.loads(store.one("SELECT report FROM rounds WHERE id=?", (second,))["report"])
    context = {
        "kind": "parent",
        "node_id": "root",
        "child_node_id": report["node_id"],
        "round_id": second,
        "goal": store.node("root")["goal"],
        "report": report,
    }
    prompt = (
        "ENGLISH_ONLY: Keep this previously queued payload byte-for-byte.\nCONTEXT_JSON\n"
        + json.dumps(context)
        + "\nOUTPUT_SCHEMA_JSON\n"
        + json.dumps(ParentRoundResponse.model_json_schema())
    )
    old_session = store.one("SELECT id FROM sessions WHERE node_id='root' AND active=1")["id"]
    session = await transport.rollover_session(old_session, "legacy-queued-replacement")
    turn_id = f"parent:{second}:e0:a0"
    transport._queue(session, prompt, turn_id)
    await scheduler._parent(second)
    assert transport.sent[-1]["prompt"] == prompt
    assert store.one("SELECT prompt FROM turns WHERE id=?", (turn_id,))["prompt"] == prompt
    third = store.one("SELECT id FROM rounds WHERE previous_round_id=?", (second,))["id"]
    await scheduler._leaf(third)
    await scheduler._parent(third)
    # A legacy queued prompt did not contain the old session's first proof.
    # Restore that unseen evidence even though this replacement is now warm.
    restored = transport.calls[-1]["context"]["restored_history"]
    assert [item["report"]["round_id"] for item in restored] == [first]
    assert "PRIOR_PROOF" in restored[0]["report"]["evidence"]


async def test_fenced_web_replies_preserve_literal_math_through_the_mandatory_pair(tmp_path):
    store = Store.initialize(
        tmp_path, "Verify a literal mathematical certificate.", Config(transport="fake")
    )
    child = store.split(
        "root", [{"goal": "Check the certificate.", "relative_weight": 1, "initial_prompt": TASK}]
    )[0]
    literal = "Sum certificate: \\sum_{j: s_j s_{j+1}>0} s_j s_{j+1}(t_{j+1}-t_j)^2.\nKeep _underscores_, *stars*, \\alpha and a second line exactly."

    def fenced(value):
        return "```json\n" + json.dumps(value) + "\n```"

    def leaf(context):
        return fenced(
            {
                "node_id": child,
                "round_id": context["round_id"],
                "status": "PARTIAL",
                "summary": "Literal certificate awaiting assessment.",
                "findings": [],
                "evidence": literal,
                "obstacles": [],
                "recommended_next_steps": [],
            }
        )

    def parent(context):
        return fenced(
            {
                "child_node_id": child,
                "responding_to_round_id": context["round_id"],
                "assessment": literal,
                "next_prompt": TASK + "\nPreserve " + literal,
            }
        )

    transport = ScriptedTransport(store, {"leaf": leaf, "parent": parent})
    scheduler = Scheduler(store, transport)
    round_id = store.one("SELECT id FROM rounds WHERE node_id=?", (child,))["id"]
    await scheduler._leaf(round_id)
    assert "single fenced JSON code block" in transport.calls[-1]["prompt"]
    assert (
        json.loads(store.one("SELECT report FROM rounds WHERE id=?", (round_id,))["report"])[
            "evidence"
        ]
        == literal
    )
    await scheduler._parent(round_id)
    assert "single fenced JSON code block" in transport.calls[-1]["prompt"]
    response = json.loads(
        store.one("SELECT payload FROM parent_responses WHERE round_id=?", (round_id,))["payload"]
    )
    assert response["assessment"] == literal
    assert response["next_prompt"] == TASK + "\nPreserve " + literal
    await scheduler.aclose()
