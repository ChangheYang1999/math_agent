"""Deterministic offline checks for recursive allocation and optional messages."""

import asyncio
import json

import pytest

from math_research_agent.config import Config
from math_research_agent.scheduler import Scheduler
from math_research_agent.schemas import PARENT_MODEL, PRO_MODEL
from math_research_agent.store import Store, digest, encode
from math_research_agent.transport import ScriptedTransport

TASK = (
    "Derive the Fibonacci addition identity from the defining recurrence, state the "
    "index conventions, and check the boundary cases before applying Euclidean reduction."
)


async def advance(scheduler, condition):
    for _ in range(100):
        if condition():
            return
        await scheduler.tick()
        await asyncio.sleep(0)
    assert condition(), scheduler.snapshot()


def pending(store, node_id, kind):
    return store.one(
        "SELECT * FROM approvals WHERE node_id=? AND artifact_type=? AND status='PENDING'",
        (node_id, kind),
    )


async def test_recursive_allocation_and_messages_at_undispatched_boundary(tmp_path):
    """Synthetic approvals below exercise the protocol; no human or web model is used."""
    store = Store.initialize(
        tmp_path,
        "Investigate the Euclidean gcd identity for Fibonacci numbers.",
        Config(transport="fake", max_active_leaves=8, manual_review_enabled=True),
    )
    tasks = [
        {"goal": goal, "relative_weight": weight, "initial_prompt": TASK}
        for goal, weight in [
            ("Derive the addition and Euclidean reduction identities.", 0.75),
            ("Check the zero-index and divisibility boundary cases.", 0.25),
        ]
    ]
    bootstrap = {"research_state": "Offline structural test; no live proof.", "children": tasks}
    transport = ScriptedTransport(store, {"bootstrap": [bootstrap]})
    scheduler = Scheduler(store, transport)
    await advance(scheduler, lambda: len(store.children("root")) == 2)
    a = next(node["id"] for node in store.children("root") if node["goal"] == tasks[0]["goal"])
    b = next(node["id"] for node in store.children("root") if node["id"] != a)
    before = store.allocation()
    prompt = pending(store, a, "prompt")
    scheduler.decide(prompt["id"], "approve", prompt["content_hash"])
    await advance(scheduler, lambda: bool(pending(store, a, "report")))
    item = pending(store, a, "report")
    scheduler.decide(item["id"], "approve", item["content_hash"])
    await advance(scheduler, lambda: bool(store.query("SELECT * FROM parent_responses")))
    report = store.one("SELECT * FROM rounds WHERE node_id=? AND report IS NOT NULL", (a,))
    original_report_hash = digest(report["report"])
    original_pro = store.one("SELECT * FROM sessions WHERE node_id=?", (a,))
    assert original_pro["model"] == PRO_MODEL
    transport.script = None  # Restoration uses the simulator's exact existing-child contract.
    grandchildren = store.split(
        a,
        [
            {"goal": goal, "relative_weight": 0.5, "initial_prompt": TASK}
            for goal in (
                "Derive the Fibonacci addition identity with explicit indices.",
                "Use the addition identity to justify Euclidean reduction.",
            )
        ],
        actor_id="root",
    )
    await advance(scheduler, lambda: store.setting("coordinator_ready:" + a))
    coordinator = store.one("SELECT * FROM sessions WHERE node_id=? AND active=1", (a,))
    assert coordinator["model"] == PARENT_MODEL and coordinator["id"] != original_pro["id"]
    assert not store.one("SELECT active FROM sessions WHERE id=?", (original_pro["id"],))["active"]
    assert (
        digest(store.one("SELECT report FROM rounds WHERE id=?", (report["id"],))["report"])
        == original_report_hash
    )
    recursive = store.allocation()
    assert recursive["root"]["active_leaves"] == 3 < recursive["root"]["leaf_capacity"] == 8
    assert [recursive[node]["leaf_capacity"] for node in grandchildren] == [3, 3]
    assert recursive[b]["leaf_capacity"] == 2
    assert len(store.query("SELECT * FROM nodes")) == 5  # Idle capacity creates no extra tasks.
    for children in (store.children("root"), store.children(a)):
        assert sum(child["relative_weight"] for child in children) == pytest.approx(1)
        for child in children:
            assert recursive[child["id"]]["absolute_weight"] == pytest.approx(
                recursive[child["parent_id"]]["absolute_weight"] * child["relative_weight"]
            )
    store.reweight("root", {a: 0.5, b: 0.5})
    down = store.allocation()
    assert down[a]["leaf_capacity"] == down[b]["leaf_capacity"] == 4
    store.reweight("root", {a: 1, b: 0})
    await advance(scheduler, lambda: store.node(b)["status"] == "PAUSED")
    zero = store.allocation()
    assert zero[b]["leaf_capacity"] == zero[b]["active_leaves"] == 0
    store.set_node_status(b, "ACTIVE")
    store.reweight("root", {a: 0.75, b: 0.25})
    resumed = store.allocation()
    assert resumed[b]["leaf_capacity"] == 2
    assert store.one("SELECT stage FROM rounds WHERE node_id=?", (b,))["stage"] == "PROMPT_APPROVAL"
    # Important coordinator communication must work while concrete next tasks remain gated.
    store.execute(
        "INSERT INTO optional_jobs(id,priority,kind,actor_id,payload) VALUES('meaningful-message',1,'message',?,?)",
        (
            a,
            encode(
                {
                    "sender_node_id": a,
                    "recipient_node_id": "root",
                    "message": "The addition identity needs an explicit zero-index convention.",
                    "reason": "Coordinate consistent boundary assumptions between branches.",
                    "evidence_reference": report["id"],
                }
            ),
        ),
    )
    await advance(
        scheduler,
        lambda: bool(
            store.one("SELECT * FROM messages WHERE id='meaningful-message' AND status='DELIVERED'")
        ),
    )
    coordination = [
        call for call in transport.calls if call["context"].get("kind") == "coordination"
    ]
    important = [call for call in coordination if "important_message" in call["context"]]
    assert len(important) == 1 and important[0]["node_id"] == "root"
    assert important[0]["context"]["important_message"]["evidence_reference"] == report["id"]
    assert all(
        "important_message" in call["context"] or "allocation" in call["context"]
        for call in coordination
    )
    await advance(scheduler, lambda: not scheduler._tasks)
    stable_calls = len(transport.calls)
    for _ in range(5):
        await scheduler.tick()
    assert len(transport.calls) == stable_calls  # No periodic internal meeting.
    leaf_calls = [call for call in transport.calls if call["context"].get("kind") == "leaf"]
    assert len(leaf_calls) == 1 and leaf_calls[0]["node_id"] == a
    # Every node retains its own section, and an unverified model claim stays proposed.
    for node, body in [
        ("root", "Overall boundary assumptions remain under investigation."),
        (a, "The addition-identity branch retains its earlier research evidence."),
    ]:
        store.update_section(
            node,
            {
                "node_id": node,
                "body": body,
                "claim_status": "MODEL_PROPOSED",
                "significant": True,
                "evidence_reference": report["id"],
            },
        )
    with pytest.raises(ValueError, match="own"):
        store.update_section(
            "root",
            {
                "node_id": a,
                "body": "Overwriting another node is invalid.",
                "claim_status": "MODEL_PROPOSED",
                "significant": True,
                "evidence_reference": report["id"],
            },
        )
    with pytest.raises(ValueError, match="independent"):
        store.update_section(
            a,
            {
                "node_id": a,
                "body": "A solved model report is not independent verification.",
                "claim_status": "VERIFIED",
                "significant": True,
                "evidence_reference": report["id"],
            },
        )
    content = store.build_report()
    assert "## 1 " in content and "### 1." in content and "#### 1." in content
    assert all(f'<a id="{node}"></a>' in content for node in ["root", a, b, *grandchildren])
    assert "MODEL_PROPOSED" in content and "Claim status: **VERIFIED**" not in content
    # Persist a small, explicitly offline audit in pytest's isolated project directory.
    (tmp_path / "offline_tree_evidence.json").write_text(
        json.dumps(
            {
                "mode": "OFFLINE_SIMULATION",
                "snapshots": {
                    "initial": before,
                    "recursive": recursive,
                    "reweighted_down": down,
                    "zero_paused": zero,
                    "resumed": resumed,
                },
                "promotion": {
                    "old_session": original_pro,
                    "coordinator_session": coordinator,
                    "preserved_report_sha256": original_report_hash,
                },
                "messages": store.query("SELECT * FROM messages"),
                "final_rounds": store.query("SELECT * FROM rounds ORDER BY seq"),
                "final_approvals": store.query("SELECT * FROM approvals ORDER BY id"),
                "final_events": store.query("SELECT * FROM events ORDER BY id"),
                "coordination": [call["context"] for call in coordination],
                "calls": [
                    {key: call[key] for key in ("node_id", "model", "session_id", "turn_id")}
                    for call in transport.calls
                ],
                "report_outline": [line for line in content.splitlines() if line.startswith("#")],
            },
            indent=2,
        )
        + "\n"
    )
    await scheduler.aclose()
