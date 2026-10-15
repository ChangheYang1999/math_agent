"""Offline protocol checks; synthetic actions here are never human approvals."""

import asyncio
import hashlib
import json
import os
import shutil
from pathlib import Path

import httpx
import pytest

from math_research_agent.config import Config
from math_research_agent.dashboard import Dashboard
from math_research_agent.parent_prompt import parent_context
from math_research_agent.scheduler import Scheduler
from math_research_agent.schemas import PARENT_MODEL
from math_research_agent.store import Store
from math_research_agent.transport import ScriptedTransport

TASK = (
    "Count ordered nonnegative integer triples whose sum is at most n. "
    "Give a rigorous bijection, state the domain of n, and check the n=0 boundary case."
)


def example(tmp_path, review=True):
    store = Store.initialize(
        tmp_path,
        TASK,
        Config(transport="fake", manual_review_enabled=review, max_active_leaves=1),
    )
    store.split("root", [{"goal": TASK, "relative_weight": 1, "initial_prompt": TASK}])
    transport = ScriptedTransport(
        store,
        {
            "translation": {"english_text": "Why is x=1 a boundary case?"},
            "discussion": {
                "reply": "Check x=1 against the stated domain before accepting evidence."
            },
            "display_translation": {
                "display_text": "请先核查 x=1 是否属于声明的范围；此解释不会批准内容。"
            },
        },
    )
    return store, transport, Scheduler(store, transport)


async def advance(scheduler, predicate):
    for _ in range(100):
        if predicate():
            return
        await scheduler.tick()
        await asyncio.sleep(0)
    assert predicate(), scheduler.snapshot()


def queued(scheduler, kind="prompt"):
    return next((a for a in scheduler.snapshot()["approvals"] if a["artifact_type"] == kind), None)


async def test_mode_on_rearms_unsent_automatic_prompt_and_unconsumed_report(tmp_path):
    store, transport, scheduler = example(tmp_path, review=False)
    round_id = store.one("SELECT id FROM rounds")["id"]
    scheduler.set_review_mode(True)
    assert store.one("SELECT stage FROM rounds")["stage"] == "PROMPT_APPROVAL"
    await scheduler._leaf(round_id)  # A previously queued local task cannot cross the new gate.
    assert not transport.sent
    prompt = queued(scheduler)
    scheduler.decide(prompt["id"], "approve", prompt["content_hash"])
    scheduler.set_review_mode(False)
    await scheduler._leaf(round_id)
    assert store.one("SELECT stage FROM rounds")["stage"] == "AWAITING_PARENT_RESPONSE"
    scheduler.set_review_mode(True)
    assert store.one("SELECT stage,report_accepted FROM rounds") == {
        "stage": "REPORT_APPROVAL",
        "report_accepted": 0,
    }
    assert queued(scheduler, "report")
    assert len(store.query("SELECT * FROM events WHERE type='review_gate_rearmed'")) == 2
    assert len(transport.calls) == 1
    await scheduler.aclose()


async def test_mode_on_preserves_parent_request_already_in_progress(tmp_path):
    store, transport, scheduler = example(tmp_path, review=False)
    round_id = store.one("SELECT id FROM rounds")["id"]
    await scheduler._leaf(round_id)
    entered, release = asyncio.Event(), asyncio.Event()

    async def parent(context):
        entered.set()
        await release.wait()
        return {
            "child_node_id": context["child_node_id"],
            "responding_to_round_id": context["round_id"],
            "assessment": "Offline assessment: verify the counting bijection independently.",
            "next_prompt": TASK,
        }

    transport.script = {"parent": parent}
    scheduler._launch(
        "parent:" + round_id, scheduler._parent(round_id), store.children("root")[0]["id"]
    )
    await asyncio.wait_for(entered.wait(), 2)
    scheduler.set_review_mode(True)
    assert store.one("SELECT stage,report_accepted FROM rounds WHERE id=?", (round_id,)) == {
        "stage": "AWAITING_PARENT_RESPONSE",
        "report_accepted": 1,
    }
    release.set()
    await advance(scheduler, lambda: bool(queued(scheduler)))
    assert queued(scheduler)["round_id"] != round_id
    assert len([c for c in transport.calls if c["context"]["kind"] == "parent"]) == 1
    await scheduler.aclose()


async def test_http_review_discussion_revision_and_immutable_correction(tmp_path):
    store, transport, scheduler = example(tmp_path)
    dashboard = Dashboard(scheduler)
    server = await asyncio.start_server(dashboard.handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server, httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
        prompt = queued(scheduler)
        html = (await client.get("/")).text
        assert 'id="reviewDialog"' in html and 'id="reviewSummary"' in html
        assert "&&!a.deferred" not in html  # Later defers this page, never all future page loads.
        original = await client.get("/review-original", params={"id": prompt["id"]})
        assert original.text == prompt["payload"]
        assert hashlib.sha256(original.content).hexdigest() == prompt["content_hash"]
        before = store.one("SELECT * FROM approvals WHERE id=?", (prompt["id"],))
        for question in ("What domain is required?", "为什么 x=1 是边界情况？"):
            response = await client.post(
                "/api/review-message",
                json={
                    "approval_id": prompt["id"],
                    "content_hash": prompt["content_hash"],
                    "comment": question,
                },
            )
            assert response.status_code == 200
            message_id = response.json()["message_id"]
            await advance(
                scheduler,
                lambda current_id=message_id: store.one(
                    "SELECT status FROM review_messages WHERE id=?", (current_id,)
                )["status"]
                == "COMPLETED",
            )
            assert store.one("SELECT * FROM approvals WHERE id=?", (prompt["id"],)) == before
            assert (
                "请先核查 x=1"
                in store.one("SELECT display_reply FROM review_messages WHERE id=?", (message_id,))[
                    "display_reply"
                ]
            )
        discussion = [c for c in transport.calls if c["context"]["kind"] == "discussion"]
        assert len(discussion) == 2 and discussion[0]["session_id"] == discussion[1]["session_id"]
        assert not [c for c in transport.calls if c["context"]["kind"] == "leaf"]

        async def decision(item, kind, comment=""):
            return await client.post(
                "/api/decision",
                json={
                    "approval_id": item["id"],
                    "content_hash": item["content_hash"],
                    "decision": kind,
                    "comment": comment,
                },
            )

        assert (await decision(prompt, "later")).status_code == 200
        assert (
            Store(tmp_path).one("SELECT deferred FROM approvals WHERE id=?", (prompt["id"],))[
                "deferred"
            ]
            == 1
        )
        assert len((await client.get("/api/state")).json()["review_messages"]) == 2
        assert (
            await decision(prompt, "request_revision", "State the exact domain before the proof.")
        ).status_code == 200
        await advance(scheduler, lambda: queued(scheduler) is not None)
        revised = queued(scheduler)
        assert revised["version"] == prompt["version"] + 1
        assert (await decision(prompt, "approve")).status_code == 400
        assert (await decision(revised, "approve")).status_code == 200  # Synthetic test action.
        await advance(scheduler, lambda: queued(scheduler, "report") is not None)
        report = queued(scheduler, "report")
        assert not store.query("SELECT * FROM parent_responses")
        assert (
            await decision(
                report, "request_revision", "Check the zero boundary in a corrective task."
            )
        ).status_code == 200
        await advance(scheduler, lambda: queued(scheduler) is not None)
        correction = queued(scheduler)
        old = store.one("SELECT * FROM rounds WHERE id=?", (report["round_id"],))
        new = store.one("SELECT * FROM rounds WHERE id=?", (correction["round_id"],))
        assert old["report"] == report["payload"] and old["report_accepted"] == 0
        assert new["previous_round_id"] == old["id"] and new["kind"] == "correction"
        assert new["stage"] == "PROMPT_APPROVAL"
        assert len([c for c in transport.calls if c["context"]["kind"] == "leaf"]) == 1
        assert (await decision(report, "approve")).status_code == 400
        parent = await scheduler._session("root", PARENT_MODEL)
        context = parent_context(
            store,
            {
                "node_id": "root",
                "child_node_id": old["node_id"],
                "round_id": new["id"],
            },
            parent,
        )
        history = context["restored_history"][0]
        assert history["report_accepted"] is False and history["response_source"] == "feedback"
        assert history["report"]["round_id"] == old["id"]
        if "prior_report_references" in context:
            assert context["prior_report_references"][0]["report_accepted"] is False
    await scheduler.aclose()


async def test_repeated_approval_ui_is_distinct_queue_and_survives_restart(tmp_path):
    """Actual JS/HTTP/DB, synthetic DOM/provider/approvals, isolated temporary data."""
    node = shutil.which("node") or os.environ.get("MATHAGENT_TEST_NODE")
    if not node:
        pytest.skip("Node is required only for the offline dashboard JS fixture")
    fixture = Path(__file__).with_name("dashboard_review_fixture.mjs")
    store, _, scheduler = example(tmp_path)
    store.set_setting("project_status", "PAUSED")

    async def browser_fixture(dashboard, *arguments):
        server = await asyncio.start_server(dashboard.handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        async with server:
            process = await asyncio.create_subprocess_exec(
                node,
                str(fixture),
                f"http://127.0.0.1:{port}",
                *arguments,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), 20)
            assert process.returncode == 0, stderr.decode()
            return json.loads(stdout)

    async def worker():
        while True:
            await scheduler.tick()
            await asyncio.sleep(0.01)

    runner = asyncio.create_task(worker())
    try:
        result = await browser_fixture(Dashboard(scheduler), "exercise")
    finally:
        runner.cancel()
        await asyncio.gather(runner, return_exceptions=True)
        await scheduler.aclose()
    assert len(set(result["distinctApproved"])) == 4
    approval_events = [
        json.loads(e["payload"])
        for e in store.query("SELECT payload FROM events WHERE type='human_decision'")
        if json.loads(e["payload"])["decision"] == "approve"
    ]
    assert len(approval_events) == 4  # Duplicate HTTP request did not add an approval.
    assert all(e["source"] == "HUMAN_APPROVED" for e in approval_events)
    assert not store.query("SELECT * FROM events WHERE type='review_gate_rearmed'")
    assert len(store.query("SELECT * FROM parent_responses")) == 2
    reopened = Store(tmp_path)
    restored = Scheduler(reopened, ScriptedTransport(reopened))
    try:
        after = await browser_fixture(
            Dashboard(restored),
            "inspect",
            result["originalId"],
            result["nextPending"],
        )
        assert after["oldApprovedNotReopened"] is True
        assert queued(restored)["id"] == result["nextPending"]
        original = reopened.one("SELECT * FROM approvals WHERE id=?", (result["originalId"],))
        assert original["status"] == "APPROVED" and original["decision"] == "approve"
    finally:
        await restored.aclose()
