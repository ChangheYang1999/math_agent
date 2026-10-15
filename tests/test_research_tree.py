"""Focused behavioral coverage for the durable Research Tree protocol."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from math_research_agent.config import Config
from math_research_agent.scheduler import Scheduler
from math_research_agent.schemas import (
    PARENT_MODEL,
    PRO_MODEL,
    LeafRoundReport,
    ParentRoundResponse,
)
from math_research_agent.store import Store, encode
from math_research_agent.transport import ScriptedTransport

SPECIFIC_PROMPT = (
    "Prove that the sum of the first n odd positive integers equals n squared. "
    "Give a rigorous induction proof, check the base case, and identify any missing hypotheses."
)


def report(node_id: str, round_id: str, **changes) -> dict:
    result = {
        "node_id": node_id,
        "round_id": round_id,
        "status": "PARTIAL",
        "summary": "The base case holds and the induction step is explicit.",
        "findings": ["Adding the next odd integer gives the next square."],
        "evidence": "For n=1 the sum is 1. The induction step adds 2n+1 to n squared.",
        "obstacles": [],
        "recommended_next_steps": ["Check the induction hypotheses independently."],
        "split_suggestion": [],
        "important_update": False,
    }
    result.update(changes)
    return result


def project(tmp_path: Path, **config_changes):
    from math_research_agent.store import Store

    config = Config(**{"transport": "fake", "target_active_leaves": 1, **config_changes})
    return Store.initialize(tmp_path, "Prove the formula for sums of odd integers.", config)


async def advance(scheduler, predicate, ticks: int = 100):
    """Allow independently scheduled tasks to finish without a wall-clock sleep."""
    for _ in range(ticks):
        if predicate():
            return
        await scheduler.tick()
        await asyncio.sleep(0)
    assert predicate(), scheduler.snapshot()


async def test_manual_relay_keeps_exact_pending_turn_without_fabricating_a_reply(tmp_path):
    from math_research_agent.transport import ManualRelayTransport, RelayPending, TransportError

    store = project(tmp_path)
    transport = ManualRelayTransport(store)
    root = store.one("SELECT id FROM nodes WHERE parent_id IS NULL")["id"]
    session = await transport.create_session(root, PARENT_MODEL, "manual-root")
    await transport.send_message(session, SPECIFIC_PROMPT, "manual-turn")
    await transport.send_message(session, SPECIFIC_PROMPT, "manual-turn")
    with pytest.raises(RelayPending):
        await transport.await_response(session, "manual-turn")
    assert len(transport.list_pending()) == 1
    assert transport.list_pending()[0]["prompt"] == SPECIFIC_PROMPT
    assert (
        store.one("SELECT raw_response FROM turns WHERE id='manual-turn'")["raw_response"] is None
    )

    # The pasted reply is bound to an explicitly selected UI model and a real chat URL.
    with pytest.raises(TransportError):
        transport.bind_session(session.id, "https://chatgpt.com/c/test", PRO_MODEL)
    session = transport.bind_session(session.id, "https://chatgpt.com/c/test", PARENT_MODEL)
    transport.mark_sent("manual-turn")
    transport.submit_response("manual-turn", "The actual response pasted by the human.")
    assert (
        await transport.await_response(session, "manual-turn")
        == "The actual response pasted by the human."
    )
    with pytest.raises(TransportError):
        transport.submit_response("manual-turn", "A different response must use a new turn.")


async def test_transport_recovery_reuses_session_and_committed_raw_reply(tmp_path):
    from math_research_agent.transport import ScriptedTransport, TransportError

    store = project(tmp_path)
    root = store.one("SELECT id FROM nodes WHERE parent_id IS NULL")["id"]
    first = ScriptedTransport(store, script=[{"answer": "Stored response"}])
    session = await first.create_session(root, PARENT_MODEL, "persistent-root")
    prompt = SPECIFIC_PROMPT + '\nCONTEXT_JSON\n{"kind":"test"}'
    await first.send_message(session, prompt, "committed-turn")
    raw = await first.await_response(session, "committed-turn")
    second = ScriptedTransport(
        store, script=[RuntimeError("Must never invoke a committed turn again")]
    )
    restored = await second.create_session(root, PARENT_MODEL, "persistent-root")
    assert restored == session
    await second.send_message(restored, prompt, "committed-turn")
    assert await second.await_response(restored, "committed-turn") == raw
    assert not second.sent and not second.calls
    assert len(store.query("SELECT * FROM turns WHERE id='committed-turn'")) == 1
    with pytest.raises(TransportError):
        await second.send_message(restored, prompt + "changed", "committed-turn")


def pending(scheduler, artifact_type: str | None = None):
    return [
        item
        for item in scheduler.snapshot()["approvals"]
        if item["status"] in {"PENDING", "LATER", "DEFERRED"}
        and (artifact_type is None or item["artifact_type"].lower() == artifact_type)
    ]


def calls(transport, kind: str):
    return [call for call in transport.calls if call["context"].get("kind") == kind]


async def test_automatic_two_round_loop_stores_solved_reports_and_parent_next_prompts(tmp_path):
    from math_research_agent.scheduler import Scheduler
    from math_research_agent.transport import ScriptedTransport

    store = project(tmp_path)
    transport = ScriptedTransport(
        store,
        {"leaf": lambda context: report(context["node_id"], context["round_id"], status="SOLVED")},
    )
    scheduler = Scheduler(store, transport)
    await scheduler.run(max_rounds=2)

    leaf_calls, parent_calls = calls(transport, "leaf"), calls(transport, "parent")
    assert len(leaf_calls) == len(parent_calls) == 2
    assert [call["context"]["round_id"] for call in leaf_calls] == [
        call["context"]["round_id"] for call in parent_calls
    ]
    assert leaf_calls[0]["session_id"] == leaf_calls[1]["session_id"]
    assert parent_calls[0]["session_id"] == parent_calls[1]["session_id"]
    assert all(call["model"] == PRO_MODEL for call in leaf_calls)
    assert all(call["model"] == PARENT_MODEL for call in parent_calls)
    assert len({call["turn_id"] for call in transport.calls}) == len(transport.calls)
    assert not pending(scheduler)
    assert len(store.query("SELECT * FROM rounds")) >= 2
    assert len(store.query("SELECT * FROM turns WHERE raw_response IS NOT NULL")) >= 5
    assert all("ENGLISH_ONLY" in call["prompt"] for call in transport.calls)
    assert not store.query("SELECT * FROM messages")


async def test_both_review_gates_are_hash_bound_durable_and_release_when_disabled(tmp_path):
    from math_research_agent.scheduler import Scheduler
    from math_research_agent.store import Store
    from math_research_agent.transport import ScriptedTransport

    store = project(tmp_path, manual_review_enabled=True)
    transport = ScriptedTransport(store)
    scheduler = Scheduler(store, transport)
    await advance(scheduler, lambda: bool(pending(scheduler, "prompt")))
    first = pending(scheduler, "prompt")[0]
    assert not calls(transport, "leaf")
    with pytest.raises(ValueError):
        scheduler.decide(first["id"], "approve", "obsolete-content-hash")
    scheduler.decide(first["id"], "later", first["content_hash"])
    await scheduler.aclose()

    reopened = Store(tmp_path)
    transport = ScriptedTransport(reopened)
    scheduler = Scheduler(reopened, transport)
    assert pending(scheduler, "prompt")[0]["id"] == first["id"]
    scheduler.decide(first["id"], "approve", first["content_hash"])
    await advance(scheduler, lambda: bool(pending(scheduler, "report")))
    original_report = pending(scheduler, "report")[0]
    assert len(calls(transport, "leaf")) == 1
    for _ in range(5):
        await scheduler.tick()
        await asyncio.sleep(0)
    assert not calls(transport, "parent")
    assert len(calls(transport, "leaf")) == 1
    scheduler.decide(original_report["id"], "approve", original_report["content_hash"])
    await advance(scheduler, lambda: bool(pending(scheduler, "prompt")))
    next_prompt = pending(scheduler, "prompt")[0]
    assert next_prompt["round_id"] != original_report["round_id"]
    assert len(calls(transport, "parent")) == 1
    assert len(calls(transport, "leaf")) == 1

    scheduler.set_review_mode(False)
    assert not pending(scheduler)
    assert any("review" in str(event).lower() for event in reopened.query("SELECT * FROM events"))
    await scheduler.aclose()


async def test_human_feedback_uses_parent_and_preserves_questioned_report(tmp_path):
    from math_research_agent.scheduler import Scheduler
    from math_research_agent.transport import ScriptedTransport

    store = project(tmp_path, manual_review_enabled=True)
    transport = ScriptedTransport(
        store,
        {
            "translation": {
                "english_text": "Check the equality condition x=1 before using this report."
            }
        },
    )
    scheduler = Scheduler(store, transport)
    await advance(scheduler, lambda: bool(pending(scheduler, "prompt")))
    initial = pending(scheduler, "prompt")[0]
    comment = "Verify the base case separately and explain the precise induction hypothesis."
    scheduler.decide(initial["id"], "request_revision", initial["content_hash"], comment)
    await advance(
        scheduler, lambda: any(item["id"] != initial["id"] for item in pending(scheduler, "prompt"))
    )
    revised = next(item for item in pending(scheduler, "prompt") if item["id"] != initial["id"])
    assert (
        revised["version"] > initial["version"]
        or revised["content_hash"] != initial["content_hash"]
    )
    with pytest.raises(ValueError, match="pending"):
        scheduler.decide(initial["id"], "approve", initial["content_hash"])
    assert not calls(transport, "leaf")
    assert comment in calls(transport, "feedback")[-1]["prompt"]
    assert calls(transport, "feedback")[-1]["model"] == PARENT_MODEL
    scheduler.decide(revised["id"], "approve", revised["content_hash"])
    await advance(scheduler, lambda: bool(pending(scheduler, "report")))
    questioned = pending(scheduler, "report")[0]
    original = store.one("SELECT payload FROM approvals WHERE id=?", (questioned["id"],))["payload"]
    scheduler.decide(
        questioned["id"],
        "request_revision",
        questioned["content_hash"],
        "请核查等号条件 x=1，再使用此报告。",
    )
    await advance(scheduler, lambda: bool(pending(scheduler, "prompt")))
    correction = pending(scheduler, "prompt")[0]
    assert correction["round_id"] != questioned["round_id"]
    assert (
        store.one("SELECT payload FROM approvals WHERE id=?", (questioned["id"],))["payload"]
        == original
    )
    assert len(calls(transport, "leaf")) == 1
    assert calls(transport, "feedback")[-1]["model"] == PARENT_MODEL
    translated = calls(transport, "translation")[-1]
    assert translated["node_id"] == "__user_translation__"
    assert "Check the equality condition x=1" in calls(transport, "feedback")[-1]["prompt"]
    assert "请核查" not in calls(transport, "feedback")[-1]["prompt"]
    await scheduler.aclose()


async def complete_reviewed_round(scheduler, node_id: str):
    prompt = next(item for item in pending(scheduler, "prompt") if item["node_id"] == node_id)
    scheduler.decide(prompt["id"], "approve", prompt["content_hash"])
    await advance(
        scheduler, lambda: any(item["node_id"] == node_id for item in pending(scheduler, "report"))
    )
    item = next(item for item in pending(scheduler, "report") if item["node_id"] == node_id)
    scheduler.decide(item["id"], "approve", item["content_hash"])
    await advance(
        scheduler,
        lambda: scheduler.store.one(
            "SELECT * FROM parent_responses WHERE round_id=?", (item["round_id"],)
        ),
    )


async def test_recursive_splits_atomic_weights_and_largest_remainder_targets(tmp_path):
    from math_research_agent.scheduler import Scheduler
    from math_research_agent.store import largest_remainder
    from math_research_agent.transport import ScriptedTransport

    store = project(tmp_path, manual_review_enabled=True, target_active_leaves=8)
    scheduler = Scheduler(store, ScriptedTransport(store))
    await advance(scheduler, lambda: bool(pending(scheduler, "prompt")))
    first = store.children("root")[0]["id"]
    tasks = [
        {
            "goal": "Verify the induction base and boundary cases.",
            "relative_weight": 0.6,
            "initial_prompt": SPECIFIC_PROMPT,
        },
        {
            "goal": "Find an independent geometric argument for the identity.",
            "relative_weight": 0.4,
            "initial_prompt": SPECIFIC_PROMPT,
        },
    ]
    with pytest.raises(ValueError, match="Finish"):
        store.split(first, tasks, actor_id="root")
    await complete_reviewed_round(scheduler, first)
    left, right = store.split(first, tasks, actor_id="root")
    await complete_reviewed_round(scheduler, left)
    grandchildren = store.split(
        left,
        [
            {
                "goal": "Check the zero and one boundary cases.",
                "relative_weight": 0.5,
                "initial_prompt": SPECIFIC_PROMPT,
            },
            {
                "goal": "Verify the induction step algebra line by line.",
                "relative_weight": 0.5,
                "initial_prompt": SPECIFIC_PROMPT,
            },
        ],
        actor_id=first,
    )

    before = {node["id"]: node["relative_weight"] for node in store.children(first)}
    with pytest.raises(ValueError):
        store.reweight(first, {left: 0.8, right: 0.8})
    assert {node["id"]: node["relative_weight"] for node in store.children(first)} == before
    store.reweight(first, {left: 0.75, right: 0.25})
    allocation = store.allocation()
    assert allocation[left]["target_leaves"] == 6
    assert allocation[right]["target_leaves"] == 2
    assert sorted(allocation[node]["target_leaves"] for node in grandchildren) == [3, 3]
    for node_id, node in allocation.items():
        children = store.children(node_id)
        if children:
            assert sum(
                allocation[child["id"]]["absolute_weight"] for child in children
            ) == pytest.approx(node["absolute_weight"])
    assert largest_remainder({"a": 0.5, "b": 0.5}, 3) == {"a": 2, "b": 1}
    store.set_node_status(right, "PAUSED")
    assert store.node(right)["status"] == "PAUSED"
    assert store.allocation()[right]["target_leaves"] == 0
    assert sum(node["relative_weight"] for node in store.children(first)) == pytest.approx(1)
    assert store.one("SELECT COUNT(*) AS n FROM sessions WHERE node_id=?", (left,))["n"] >= 1
    with pytest.raises(ValueError):
        store.reweight(first, {left: 0.5, right: 0.5})
    store.set_node_status(right, "ACTIVE")
    assert store.active(right)
    assert store.allocation()[right]["target_leaves"] > 0
    await scheduler.aclose()


async def test_report_sections_mirror_tree_and_only_owner_can_publish_significant_updates(tmp_path):
    from math_research_agent.scheduler import Scheduler
    from math_research_agent.transport import ScriptedTransport

    store = project(tmp_path)
    scheduler = Scheduler(store, ScriptedTransport(store))
    await scheduler.run(max_rounds=1)
    leaf = store.children("root")[0]["id"]
    before = (tmp_path / "RESEARCH_REPORT.md").read_text()
    update = {
        "node_id": leaf,
        "body": "The induction step reduces to n squared plus 2n plus 1.",
        "claim_status": "MODEL_PROPOSED",
        "significant": False,
        "evidence_reference": "A recorded induction calculation.",
    }
    assert not store.update_section(leaf, update)
    assert (tmp_path / "RESEARCH_REPORT.md").read_text() == before
    assert not store.query("SELECT * FROM messages")
    with pytest.raises(ValueError, match="own"):
        store.update_section("root", {**update, "significant": True})
    with pytest.raises(ValueError, match="independent"):
        store.update_section(leaf, {**update, "significant": True, "claim_status": "VERIFIED"})
    assert store.update_section(leaf, {**update, "significant": True})
    content = store.build_report()
    assert f'<a id="{leaf}"></a>' in content
    assert "## 1 " in content and "### 1.1 " in content
    assert update["body"] in content
    assert "MODEL_PROPOSED" in content
    assert not store.query("SELECT * FROM sections WHERE node_id='root'")
    store.set_node_status(leaf, "PAUSED")
    assert update["body"] in store.build_report()


async def test_invalid_language_is_repaired_or_held_with_every_raw_reply_preserved(tmp_path):
    from math_research_agent.scheduler import Scheduler
    from math_research_agent.transport import ScriptedTransport

    def bad(context):
        return report(context["node_id"], context["round_id"], summary="需要核查证明")

    def good(context):
        return report(context["node_id"], context["round_id"])

    store = project(tmp_path / "repaired", format_retries=1)
    transport = ScriptedTransport(store, {"leaf": [bad, good]})
    scheduler = Scheduler(store, transport)
    await scheduler.run(max_rounds=1)
    assert len(calls(transport, "leaf")) == 2
    assert len(calls(transport, "parent")) == 1
    from math_research_agent.schemas import require_english

    for call in transport.calls:
        require_english(call["prompt"])
    raw_rows = store.query("SELECT raw_response FROM turns WHERE raw_response IS NOT NULL")
    assert any(
        "需要核查证明" in json.dumps(json.loads(row["raw_response"]), ensure_ascii=False)
        for row in raw_rows
    )
    stored_report = store.one("SELECT report FROM rounds WHERE report IS NOT NULL")["report"]
    assert (
        LeafRoundReport.model_validate_json(stored_report).summary
        == good({"node_id": "unused", "round_id": "unused"})["summary"]
    )

    held_store = project(tmp_path / "held", format_retries=1)
    held_transport = ScriptedTransport(held_store, {"leaf": [bad, bad]})
    held = Scheduler(held_store, held_transport)
    await advance(
        held, lambda: bool(held_store.query("SELECT * FROM nodes WHERE runtime_state='ERROR'"))
    )
    assert len(calls(held_transport, "leaf")) == 2
    assert not calls(held_transport, "parent")
    assert not held_store.query("SELECT * FROM rounds WHERE report IS NOT NULL")
    assert held_store.query("SELECT * FROM errors WHERE resolved=0")
    await held.aclose()


async def test_restart_after_stored_report_finishes_parent_obligation_without_research_replay(
    tmp_path,
):
    from math_research_agent.scheduler import Scheduler
    from math_research_agent.store import Store
    from math_research_agent.transport import ScriptedTransport

    store = project(tmp_path, manual_review_enabled=True)
    transport = ScriptedTransport(store)
    scheduler = Scheduler(store, transport)
    await advance(scheduler, lambda: bool(pending(scheduler, "prompt")))
    initial = pending(scheduler, "prompt")[0]
    scheduler.decide(initial["id"], "approve", initial["content_hash"])
    await advance(scheduler, lambda: bool(pending(scheduler, "report")))
    review = pending(scheduler, "report")[0]
    original = store.one("SELECT report FROM rounds WHERE id=?", (review["round_id"],))["report"]
    scheduler.decide(review["id"], "approve", review["content_hash"])
    await scheduler.aclose()

    reopened = Store(tmp_path)
    recovered_transport = ScriptedTransport(reopened)
    recovered = Scheduler(reopened, recovered_transport)
    recovered.recover()
    await advance(
        recovered,
        lambda: bool(
            reopened.one("SELECT * FROM parent_responses WHERE round_id=?", (review["round_id"],))
        ),
    )
    assert not calls(recovered_transport, "leaf")
    assert len(calls(recovered_transport, "parent")) == 1
    assert (
        reopened.one("SELECT report FROM rounds WHERE id=?", (review["round_id"],))["report"]
        == original
    )
    assert (
        len(
            reopened.query("SELECT * FROM parent_responses WHERE round_id=?", (review["round_id"],))
        )
        == 1
    )
    assert len(pending(recovered, "prompt")) == 1
    await recovered.aclose()


async def test_fast_leaf_reaches_its_parent_while_another_leaf_is_still_solving(tmp_path):
    from math_research_agent.scheduler import Scheduler
    from math_research_agent.transport import ScriptedTransport

    store = project(tmp_path, target_active_leaves=2, max_concurrent_pro_turns=2)
    release_slow = asyncio.Event()
    slow_goal = "Verify the induction step for the odd integer identity."

    async def leaf_reply(context):
        if context["goal"] == slow_goal:
            await release_slow.wait()
        return report(context["node_id"], context["round_id"])

    bootstrap = {
        "research_state": "Check two distinct aspects of the proposed identity.",
        "children": [
            {"goal": slow_goal, "relative_weight": 0.5, "initial_prompt": SPECIFIC_PROMPT},
            {
                "goal": "Compute the first three square sums explicitly.",
                "relative_weight": 0.5,
                "initial_prompt": SPECIFIC_PROMPT,
            },
        ],
    }
    transport = ScriptedTransport(store, {"bootstrap": bootstrap, "leaf": leaf_reply})
    scheduler = Scheduler(store, transport)
    await advance(scheduler, lambda: bool(store.query("SELECT * FROM parent_responses")))
    slow = next(node for node in store.children("root") if node["goal"] == slow_goal)
    assert (
        store.one("SELECT stage FROM rounds WHERE node_id=? ORDER BY seq LIMIT 1", (slow["id"],))[
            "stage"
        ]
        == "SOLVING"
    )
    assert any(call["context"]["node_id"] != slow["id"] for call in calls(transport, "leaf"))
    assert not store.query(
        "SELECT * FROM parent_responses p JOIN rounds r ON r.id=p.round_id WHERE r.node_id=?",
        (slow["id"],),
    )

    # A project stop still discharges the already-running leaf's parent obligation.
    store.set_setting("project_status", "PAUSED")
    release_slow.set()
    await advance(
        scheduler,
        lambda: bool(
            store.query(
                "SELECT * FROM parent_responses p JOIN rounds r ON r.id=p.round_id WHERE r.node_id=?",
                (slow["id"],),
            )
        ),
    )
    slow_next = store.one(
        "SELECT r.* FROM parent_responses p JOIN rounds old ON old.id=p.round_id JOIN rounds r ON r.id=p.next_round_id WHERE old.node_id=?",
        (slow["id"],),
    )
    assert slow_next["stage"] == "PROMPT_READY"
    assert slow_next["prompt"]
    await scheduler.aclose()


async def test_parent_next_prompt_is_persisted_before_optional_report_work(tmp_path):
    from math_research_agent.scheduler import Scheduler
    from math_research_agent.store import encode
    from math_research_agent.transport import ScriptedTransport

    store = project(tmp_path, manual_review_enabled=True)
    scheduler = Scheduler(store, ScriptedTransport(store))
    await advance(scheduler, lambda: bool(pending(scheduler, "prompt")))
    prompt = pending(scheduler, "prompt")[0]
    scheduler.decide(prompt["id"], "approve", prompt["content_hash"])
    await advance(scheduler, lambda: bool(pending(scheduler, "report")))
    review = pending(scheduler, "report")[0]
    payload = {
        "node_id": "root",
        "body": "A significant reduction deserves a separately labeled coordinator section.",
        "claim_status": "MODEL_PROPOSED",
        "significant": True,
        "evidence_reference": review["round_id"],
    }
    store.execute(
        "INSERT INTO optional_jobs(id,priority,kind,actor_id,payload) VALUES('queued-report',2,'section','root',?)",
        (encode(payload),),
    )
    scheduler.decide(review["id"], "approve", review["content_hash"])
    await advance(
        scheduler,
        lambda: bool(
            store.one("SELECT * FROM parent_responses WHERE round_id=?", (review["round_id"],))
        ),
    )
    response = store.one("SELECT * FROM parent_responses WHERE round_id=?", (review["round_id"],))
    assert store.one("SELECT prompt FROM rounds WHERE id=?", (response["next_round_id"],))["prompt"]
    assert not store.query("SELECT * FROM sections WHERE node_id='root'")
    await advance(
        scheduler, lambda: bool(store.query("SELECT * FROM sections WHERE node_id='root'"))
    )
    events = store.query("SELECT * FROM events ORDER BY id")
    stored_index = next(
        i for i, event in enumerate(events) if event["type"] == "parent_response_stored"
    )
    published_index = next(
        i for i, event in enumerate(events) if event["type"] == "section_updated"
    )
    assert stored_index < published_index
    await scheduler.aclose()


async def test_promoted_leaf_bootstraps_its_own_coordinator_before_child_dispatch(tmp_path):
    from math_research_agent.scheduler import Scheduler
    from math_research_agent.transport import ScriptedTransport

    store = project(tmp_path, manual_review_enabled=True, target_active_leaves=2)
    restoring, release = asyncio.Event(), asyncio.Event()

    async def bootstrap(context):
        children = context.get("existing_children")
        if children:
            restoring.set()
            await release.wait()
        return {
            "research_state": "Preserve the durable task state while coordinating these children.",
            "children": children
            or [{"goal": context["goal"], "relative_weight": 1, "initial_prompt": SPECIFIC_PROMPT}],
        }

    transport = ScriptedTransport(store, {"bootstrap": bootstrap})
    scheduler = Scheduler(store, transport)
    await advance(scheduler, lambda: bool(pending(scheduler, "prompt")))
    promoted = store.children("root")[0]["id"]
    await complete_reviewed_round(scheduler, promoted)
    original_session = store.one(
        "SELECT * FROM sessions WHERE node_id=? AND model=?", (promoted, PRO_MODEL)
    )
    children = store.split(
        promoted,
        [
            {
                "goal": "Check the induction base for the identity.",
                "relative_weight": 0.5,
                "initial_prompt": SPECIFIC_PROMPT,
            },
            {
                "goal": "Check the induction step for the identity.",
                "relative_weight": 0.5,
                "initial_prompt": SPECIFIC_PROMPT,
            },
        ],
        actor_id="root",
    )
    for item in pending(scheduler, "prompt"):
        scheduler.decide(item["id"], "approve", item["content_hash"])
    await advance(scheduler, restoring.is_set)
    assert len(calls(transport, "leaf")) == 1
    restoration = next(
        call for call in calls(transport, "bootstrap") if call["node_id"] == promoted
    )
    assert restoration["model"] == PARENT_MODEL
    assert len(restoration["context"]["existing_children"]) == 2
    assert restoration["session_id"] != original_session["id"]
    assert (
        store.one("SELECT active FROM sessions WHERE id=?", (original_session["id"],))["active"]
        == 0
    )
    release.set()
    await advance(
        scheduler, lambda: any(call["node_id"] in children for call in calls(transport, "leaf"))
    )
    assert store.setting("coordinator_ready:" + promoted)
    assert store.one("SELECT * FROM sessions WHERE id=?", (original_session["id"],))
    events = store.query("SELECT * FROM events ORDER BY id")
    restored = next(i for i, event in enumerate(events) if event["type"] == "coordinator_restored")
    dispatched = next(
        i
        for i, event in enumerate(events)
        if event["type"] == "leaf_dispatched"
        and json.loads(event["payload"])["node_id"] in children
    )
    assert restored < dispatched
    await scheduler.aclose()


async def test_uncertain_leaf_delivery_recovers_same_turn_after_actual_reply_arrives(tmp_path):
    from math_research_agent.scheduler import Scheduler
    from math_research_agent.transport import ScriptedTransport, TransportError

    store = project(tmp_path)

    class UncertainTransport(ScriptedTransport):
        def __init__(self, store):
            super().__init__(store)
            self.deliveries = []

        async def send_message(self, session, prompt, turn_id):
            if session.model == PRO_MODEL:
                self.deliveries.append(turn_id)
            await super().send_message(session, prompt, turn_id)

        async def await_response(self, session, turn_id):
            if (
                session.model == PRO_MODEL
                and self.store.one("SELECT raw_response FROM turns WHERE id=?", (turn_id,))[
                    "raw_response"
                ]
                is None
            ):
                raise TransportError("The send may have completed; delivery status is uncertain.")
            return await super().await_response(session, turn_id)

    transport = UncertainTransport(store)
    scheduler = Scheduler(store, transport)
    await advance(
        scheduler, lambda: bool(store.query("SELECT * FROM nodes WHERE runtime_state='ERROR'"))
    )
    original_turn = store.one(
        "SELECT turns.* FROM turns JOIN sessions ON sessions.id=turns.session_id WHERE sessions.model=?",
        (PRO_MODEL,),
    )
    original_round = store.one("SELECT * FROM rounds WHERE stage='SOLVING'")
    assert original_turn["raw_response"] is None
    scheduler.recover()
    await advance(
        scheduler, lambda: bool(store.query("SELECT * FROM nodes WHERE runtime_state='ERROR'"))
    )
    assert transport.deliveries == [original_turn["id"]]
    await scheduler.aclose()
    store.set_setting("project_status", "PAUSED")
    actual_reply = json.dumps(report(original_round["node_id"], original_round["id"]))
    store.execute(
        "UPDATE turns SET raw_response=?,status='COMPLETED' WHERE id=?",
        (actual_reply, original_turn["id"]),
    )
    recovered = Scheduler(store, transport)
    recovered.recover()
    assert store.setting("retry:leaf:" + original_round["id"], 0) == 0
    await advance(
        recovered,
        lambda: bool(
            store.one("SELECT * FROM parent_responses WHERE round_id=?", (original_round["id"],))
        ),
    )
    assert transport.deliveries == [original_turn["id"]]
    assert (
        len(
            store.query(
                "SELECT * FROM turns WHERE id LIKE ?", ("leaf:" + original_round["id"] + ":%",)
            )
        )
        == 1
    )
    assert store.one("SELECT report FROM rounds WHERE id=?", (original_round["id"],))["report"]
    await recovered.aclose()


async def test_later_parent_control_action_blocks_next_round_until_applied(tmp_path):
    from math_research_agent.scheduler import Scheduler
    from math_research_agent.transport import ScriptedTransport

    for action, status in (("pause", "PAUSED"), ("complete", "COMPLETED")):
        store = project(tmp_path / action)

        def parent(context, selected_action=action):
            return {
                "child_node_id": context["child_node_id"],
                "responding_to_round_id": context["round_id"],
                "assessment": "Preserve the next task, then stop further dispatch at this round boundary.",
                "next_prompt": SPECIFIC_PROMPT,
                "proposed_tree_actions": [
                    {
                        "type": "reweight",
                        "node_id": "root",
                        "weights": {context["child_node_id"]: 1},
                    },
                    {"type": selected_action, "node_id": context["child_node_id"]},
                ],
            }

        transport = ScriptedTransport(store, {"parent": parent})
        scheduler = Scheduler(store, transport)
        await advance(
            scheduler,
            lambda current_store=store: bool(current_store.query("SELECT * FROM parent_responses")),
        )
        response = store.one("SELECT * FROM parent_responses")
        next_round = store.one("SELECT * FROM rounds WHERE id=?", (response["next_round_id"],))
        assert next_round["prompt"] and next_round["stage"] == "PROMPT_READY"
        await (
            scheduler.tick()
        )  # Applies the first P1 job; the later pause/complete still owns this boundary.
        assert store.node(next_round["node_id"])["status"] == "ACTIVE"
        assert len(calls(transport, "leaf")) == 1
        await advance(
            scheduler,
            lambda current_store=store, selected_round=next_round, expected_status=status: (
                current_store.node(selected_round["node_id"])["status"] == expected_status
            ),
        )
        assert len(calls(transport, "leaf")) == 1
        assert (
            store.one("SELECT prompt FROM rounds WHERE id=?", (next_round["id"],))["prompt"]
            == next_round["prompt"]
        )
        await scheduler.aclose()


def test_required_contracts_reject_missing_next_prompt_and_nonenglish_research():
    valid = report("leaf", "round")
    assert LeafRoundReport.model_validate(valid).round_id == "round"
    parent = {
        "child_node_id": "leaf",
        "responding_to_round_id": "round",
        "assessment": "The argument merits an independent verification round.",
        "next_prompt": SPECIFIC_PROMPT,
    }
    assert ParentRoundResponse.model_validate(parent).next_prompt == SPECIFIC_PROMPT
    for bad in ("", "continue working"):
        with pytest.raises(ValidationError):
            ParentRoundResponse.model_validate({**parent, "next_prompt": bad})
    with pytest.raises(ValidationError):
        ParentRoundResponse.model_validate(
            {key: value for key, value in parent.items() if key != "next_prompt"}
        )
    with pytest.raises(ValidationError, match="ENGLISH_ONLY"):
        LeafRoundReport.model_validate({**valid, "summary": "请继续证明"})


async def test_asking_parent_twice_preserves_exact_pending_artifact_and_survives_restart(tmp_path):
    from math_research_agent.scheduler import Scheduler
    from math_research_agent.store import Store
    from math_research_agent.transport import ScriptedTransport

    store = project(tmp_path, manual_review_enabled=True)
    transport = ScriptedTransport(
        store,
        {
            "discussion": lambda context: {
                "reply": "Parent advice about x=1: " + context["question"]
            },
            "translation": {"english_text": "Why does x=1 need independent verification?"},
            "display_translation": {
                "display_text": "家长建议：x=1 需要独立核查；此回复不批准报告。"
            },
        },
    )
    scheduler = Scheduler(store, transport)
    await advance(scheduler, lambda: bool(pending(scheduler, "prompt")))
    artifact = pending(scheduler, "prompt")[0]
    before = store.one("SELECT * FROM approvals WHERE id=?", (artifact["id"],))
    round_before = store.one("SELECT * FROM rounds WHERE id=?", (artifact["round_id"],))
    state_before = store.node("root")["research_state"]
    for question in ("What precise assumptions does this task use?", "为什么 x=1 需要独立核查？"):
        message_id = scheduler.ask_parent(artifact["id"], artifact["content_hash"], question)
        await advance(
            scheduler,
            lambda current_id=message_id: (
                store.one("SELECT status FROM review_messages WHERE id=?", (current_id,))["status"]
                == "COMPLETED"
            ),
        )
        assert store.one("SELECT * FROM approvals WHERE id=?", (artifact["id"],)) == before
        assert store.one("SELECT * FROM rounds WHERE id=?", (artifact["round_id"],)) == round_before
        assert store.node("root")["research_state"] == state_before
        assert not calls(transport, "leaf") and not store.query("SELECT * FROM feedback")
    discussions = calls(transport, "discussion")
    assert len(discussions) == 2
    assert discussions[0]["session_id"] == discussions[1]["session_id"]
    assert all(c["model"] == PARENT_MODEL for c in discussions)
    assert discussions[1]["context"]["question"] == "Why does x=1 need independent verification?"
    assert len(discussions[1]["context"]["discussion_history"]) == 1
    history = store.query("SELECT * FROM review_messages ORDER BY seq")
    assert "x=1" in history[1]["reply"] and "x=1" in history[1]["display_reply"]
    await scheduler.aclose()
    reopened = Store(tmp_path)
    assert reopened.query("SELECT * FROM review_messages ORDER BY seq") == history
    recovered = Scheduler(reopened, ScriptedTransport(reopened))
    assert recovered.snapshot()["review_messages"] == history
    recovered.decide(artifact["id"], "approve", artifact["content_hash"])
    await advance(recovered, lambda: bool(pending(recovered, "report")))
    assert pending(recovered, "report")[0]["round_id"] == artifact["round_id"]
    await recovered.aclose()


async def test_failed_optional_tree_job_does_not_block_unrelated_p0_work(tmp_path):
    from math_research_agent.scheduler import Scheduler
    from math_research_agent.store import encode
    from math_research_agent.transport import ScriptedTransport

    store = project(tmp_path, target_active_leaves=2)
    bootstrap = {
        "research_state": "Two distinct checks are mathematically useful.",
        "children": [
            {"goal": goal, "relative_weight": 0.5, "initial_prompt": SPECIFIC_PROMPT}
            for goal in ("Verify the base cases.", "Verify the induction step.")
        ],
    }
    transport = ScriptedTransport(store, {"bootstrap": bootstrap})
    scheduler = Scheduler(store, transport)
    await advance(scheduler, lambda: len(store.children("root")) == 2)
    left, right = [n["id"] for n in store.children("root")]
    bad = {"type": "reweight", "node_id": "root", "weights": {left: 0.8, right: 0.8}}
    pause = {"type": "pause", "node_id": left}
    for job_id, payload in [("a-failing-reweight", bad), ("b-conflicting-pause", pause)]:
        store.execute(
            "INSERT INTO optional_jobs(id,priority,kind,actor_id,payload) VALUES(?,1,?,?,?)",
            (job_id, "tree", "root", encode(payload)),
        )
    await advance(scheduler, lambda: bool(store.query("SELECT * FROM parent_responses")))
    assert (
        store.one("SELECT status FROM optional_jobs WHERE id='a-failing-reweight'")["status"]
        == "ERROR"
    )
    assert store.query("SELECT * FROM errors WHERE resolved=0")
    assert any(c["node_id"] == right for c in calls(transport, "leaf"))
    assert not any(c["node_id"] == left for c in calls(transport, "leaf"))
    assert not store.query("SELECT * FROM nodes WHERE runtime_state='ERROR'")
    response = store.one("SELECT * FROM parent_responses")
    assert store.one("SELECT prompt FROM rounds WHERE id=?", (response["next_round_id"],))["prompt"]
    await scheduler.aclose()


async def test_unused_capacity_never_creates_placeholder_tasks(tmp_path):
    store = project(tmp_path, target_active_leaves=20)
    scheduler = Scheduler(store, ScriptedTransport(store))
    await scheduler.run(max_rounds=4)
    root = store.allocation()["root"]
    assert root["leaf_capacity"] == root["target_leaves"] == 20
    assert root["active_leaves"] == 1
    assert root["unused_capacity"] == root["underfilled"] == 19
    assert len(store.children("root")) == 1
    assert not store.query("SELECT * FROM optional_jobs WHERE kind='tree'")


def test_split_refuses_tasks_exceeding_allocated_capacity_without_mutating_tree(tmp_path):
    store = project(tmp_path, target_active_leaves=1)
    children = [
        {"goal": goal, "relative_weight": 0.5, "initial_prompt": SPECIFIC_PROMPT}
        for goal in ("Check the induction base.", "Check the induction step.")
    ]
    with pytest.raises(ValueError, match="capacity 1"):
        store.split("root", children, actor_id="root")
    assert not store.children("root")
    assert not store.query("SELECT * FROM rounds")
    assert not store.query("SELECT * FROM approvals")
    assert not store.query("SELECT * FROM events WHERE type='split'")
    assert Config(max_active_leaves=20).target_active_leaves == 20
    assert Config(target_active_leaves=20).max_active_leaves == 20


async def test_contraction_finishes_running_leaf_and_pauses_only_at_safe_boundary(tmp_path):
    store = project(tmp_path, target_active_leaves=2, max_concurrent_pro_turns=2)
    release = asyncio.Event()
    started = set()

    async def leaf(context):
        started.add(context["node_id"])
        await release.wait()
        return report(context["node_id"], context["round_id"])

    bootstrap = {
        "research_state": "Investigate the base case and induction step independently.",
        "children": [
            {"goal": goal, "relative_weight": 0.5, "initial_prompt": SPECIFIC_PROMPT}
            for goal in ("Check the induction base.", "Check the induction step.")
        ],
    }
    scheduler = Scheduler(store, ScriptedTransport(store, {"bootstrap": bootstrap, "leaf": leaf}))
    await advance(scheduler, lambda: len(started) == 2)
    left, right = [child["id"] for child in store.children("root")]
    original_round = store.one("SELECT * FROM rounds WHERE node_id=?", (right,))
    store.reweight("root", {left: 0.99, right: 0.01})
    assert store.allocation()[right]["leaf_capacity"] == 0
    await scheduler.tick()
    assert store.node(right)["status"] == "ACTIVE"
    assert (
        store.one("SELECT stage FROM rounds WHERE id=?", (original_round["id"],))["stage"]
        == "SOLVING"
    )
    release.set()
    await advance(scheduler, lambda: store.node(right)["status"] == "PAUSED")
    response = store.one("SELECT * FROM parent_responses WHERE round_id=?", (original_round["id"],))
    assert response
    assert store.one("SELECT report FROM rounds WHERE id=?", (original_round["id"],))["report"]
    next_round = store.one("SELECT * FROM rounds WHERE id=?", (response["next_round_id"],))
    assert next_round["stage"] == "PROMPT_READY" and next_round["prompt"]
    assert (
        len(store.query("SELECT * FROM turns WHERE id LIKE ?", (f"leaf:{next_round['id']}:%",)))
        == 0
    )
    await scheduler.aclose()


async def test_v1_database_upgrade_keeps_research_and_existing_bindings(tmp_path):
    store = project(tmp_path, target_active_leaves=8)
    scheduler = Scheduler(store, ScriptedTransport(store))
    await scheduler.run(max_rounds=2)
    legacy_config = {
        key: value
        for key, value in store.config.model_dump(mode="json").items()
        if not key.startswith("bridge_")
    }
    store.set_setting("config", legacy_config)
    tables = ("nodes", "rounds", "parent_responses", "artifacts", "approvals", "sections")
    before = {name: store.query(f"SELECT * FROM {name}") for name in tables}
    sessions = store.query("SELECT id,node_id,model,url,active,created_at FROM sessions")
    turns = store.query(
        "SELECT id,session_id,prompt,raw_response,status,error,created_at FROM turns"
    )
    with sqlite3.connect(store.path) as connection:
        connection.execute("DROP TABLE review_messages")
        connection.execute("DROP INDEX active_bridge_tab")
        connection.execute("DROP INDEX active_bridge_chat")
        for name in (
            "bridge_session_id",
            "bridge_client_id",
            "bridge_model",
            "bridge_effort",
            "bridge_state",
        ):
            connection.execute(f"ALTER TABLE sessions DROP COLUMN {name}")
        connection.execute("ALTER TABLE turns DROP COLUMN bridge_request_id")
        connection.execute("PRAGMA user_version=1")
    reopened = Store(tmp_path)
    assert reopened.one("PRAGMA user_version")["user_version"] == 2
    assert reopened.config.max_active_leaves == 8
    assert reopened.setting("config") == legacy_config
    assert {name: reopened.query(f"SELECT * FROM {name}") for name in tables} == before
    assert reopened.query("SELECT id,node_id,model,url,active,created_at FROM sessions") == sessions
    assert (
        reopened.query(
            "SELECT id,session_id,prompt,raw_response,status,error,created_at FROM turns"
        )
        == turns
    )
    assert not reopened.query("SELECT * FROM review_messages")
    assert all(row["bridge_request_id"] is None for row in reopened.query("SELECT * FROM turns"))
    assert "bridge_api_token" not in encode(reopened.config)
    assert Store(tmp_path).query("SELECT id FROM sessions") == reopened.query(
        "SELECT id FROM sessions"
    )
