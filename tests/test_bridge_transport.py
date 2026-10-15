"""Focused mock-HTTP coverage of the verified durable browser bridge protocol."""

import json

import httpx
import pytest

from math_research_agent.bridge_transport import BridgeTransport
from math_research_agent.config import Config
from math_research_agent.store import Store
from math_research_agent.transport import (
    COORDINATOR_MODEL,
    PRO_MODEL,
    ManualRelayTransport,
    TransportError,
)


class Events(httpx.AsyncByteStream):
    def __init__(self, values):
        self.values = values

    async def __aiter__(self):
        for name, value in self.values:
            yield f"event: {name}\ndata: {json.dumps(value)}\n\n".encode()


class BridgeServer:
    """Shapes from routes.js + turnManager.js, not an inference API mock."""

    def __init__(self):
        self.models = [
            {"id": "model-gpt-6-thinking", "label": "GPT-6 Thinking", "value": "GPT-6 Thinking"},
            {"id": "model-gpt-6-pro", "label": "GPT-6 Pro", "value": "GPT-6 Pro"},
        ]
        self.efforts = [{"id": "xhigh", "label": "Extra High", "value": "xhigh"}]
        self.clients = [{"id": "setup-tab", "ready": True, "url": "https://chatgpt.com/"}]
        self.selected = "setup-tab"
        self.current_model = self.models[0]
        self.current_effort = self.efforts[0]
        self.turns = {}
        self.turn_events = {}
        self.sent = []
        self.opens = 0
        self.lose_ack = False
        self.discard_dispatch = False
        self.requests = []

    def handle(self, request):
        self.requests.append(request)
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        if path == "/health":
            result = {"ok": True, "clients": len(self.clients)}
        elif path == "/browser/clients":
            result = {"ok": True, "clients": self.clients, "selectedClientId": self.selected}
        elif path == "/browser/tabs/open":
            self.opens += 1
            client = {
                "id": f"dedicated-{self.opens}",
                "ready": True,
                "compatible": True,
                "url": body["url"],
                "session": {"id": "new", "url": body["url"]},
            }
            self.clients.append(client)
            result = {
                "ok": True,
                "client": client,
                "sourceClientId": "setup-tab",
                "launchToken": body["launchToken"],
            }
        elif path == "/browser/select":
            self.selected = body["clientId"]
            result = {
                "ok": True,
                "selectedClient": next(c for c in self.clients if c["id"] == self.selected),
            }
        elif path == "/models":
            result = {"ok": True, "models": self.models, "current": self.current_model}
        elif path == "/efforts":
            result = {"ok": True, "efforts": self.efforts, "current": self.current_effort}
        elif path == "/sessions":
            result = {"ok": True, "sessions": []}
        elif path == "/turns" and request.method == "POST":
            self.sent.append(body)
            turn = {
                "id": body["id"],
                "status": "running",
                "input": {
                    key: value.strip() if isinstance(value, str) else value
                    for key, value in body.items()
                    if key != "id"
                },
            }
            if not self.discard_dispatch:
                self.turns[body["id"]] = turn
            if self.lose_ack:
                raise httpx.ReadTimeout("lost acknowledgement", request=request)
            result = {
                "ok": True,
                "reused": False,
                "turn": turn,
                "eventsUrl": f"/turns/{body['id']}/events",
            }
            return httpx.Response(202, json=result)
        elif path.startswith("/turns/"):
            turn_id = path.split("/")[2]
            if turn_id not in self.turns:
                return httpx.Response(404, json={"detail": "Turn not found"})
            turn = self.turns[turn_id]
            if path.endswith("/events"):
                if request.url.params.get("stream") != "1":
                    return httpx.Response(
                        200, json={"ok": True, "events": self.turn_events.get(turn_id, [])}
                    )
                self.complete(turn_id)
                stream = Events(
                    [
                        ("ready", {"turnId": turn_id, "listening": True}),
                        (
                            "event",
                            {
                                "type": "item/agentMessage/delta",
                                "turnId": turn_id,
                                "data": {"text": "interim fragment"},
                            },
                        ),
                        (
                            "event",
                            {
                                "type": "request.result",
                                "turnId": "other-request",
                                "result": {"answer": "wrong turn"},
                            },
                        ),
                        (
                            "event",
                            {"type": "turn/completed", "turnId": turn_id, "data": {"turn": turn}},
                        ),
                        ("done", {"event": {"type": "turn/completed"}}),
                    ]
                )
                return httpx.Response(
                    200, headers={"content-type": "text/event-stream"}, stream=stream
                )
            result = {"ok": True, "turn": turn, "items": []}
        else:
            raise AssertionError(f"Unexpected bridge call: {request.method} {path}")
        return httpx.Response(200, json=result)

    def complete(self, turn_id):
        turn = self.turns[turn_id]
        inp = turn["input"]
        session_id = inp["sessionId"] or "chat-" + inp["sourceClientId"]
        url = f"https://chatgpt.com/c/{session_id}"
        client = next(c for c in self.clients if c["id"] == inp["sourceClientId"])
        client.update(url=url, session={"id": session_id, "url": url})
        response = {
            "id": turn_id,
            "requestId": turn_id,
            "answer": '{"reply":"Complete English answer with \\u03bb."}',
            "session": {"id": session_id, "url": url},
            "url": url,
            "sourceClientId": inp["sourceClientId"],
            "model": inp["model"],
            "effort": inp["effort"],
            "events": [
                {
                    "type": "model.apply.done",
                    "modelApplied": True,
                    "effortApplied": bool(inp["effort"]),
                    "intelligence": {
                        "selectedModel": self.current_model,
                        "selectedEffort": self.current_effort,
                    },
                }
            ],
        }
        turn.update(
            status="completed",
            output={"type": "text", "answer": response["answer"], "response": response},
        )


def setup(tmp_path):
    store = Store.initialize(tmp_path, "Prove a precise inequality.", Config(transport="bridge"))
    server = BridgeServer()
    return store, server, httpx.MockTransport(server.handle)


async def test_bridge_exact_roles_terminal_response_and_persistent_independent_chats(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MATHAGENT_BRIDGE_API_TOKEN", "local-http-token")
    store, server, http = setup(tmp_path)
    bridge = BridgeTransport(store, http_transport=http)
    health = await bridge.diagnose()
    assert health["connected"] and health["available"] and not health["live_verified"]
    # Upstream fuzzy selectors match High before xhigh in this real UI shape.
    # The adapter must retain exact preselected Extra High without invoking it.
    server.efforts.insert(0, {"id": "high", "label": "High", "value": "high"})
    parent = await bridge.create_session("root", COORDINATOR_MODEL, "parent")
    prompt = "Exact approved English prompt.\nPreserve \\(x^2\\) verbatim."
    await bridge.send_message(parent, prompt, "parent-turn")
    response = await bridge.await_response(parent, "parent-turn")
    assert json.loads(response)["reply"].startswith("Complete English answer")
    assert server.sent[0]["message"] == prompt
    assert server.sent[0]["model"] == server.sent[0]["effort"] == ""
    assert server.sent[0]["metadata"]["requiredModel"] == "model-gpt-6-thinking"
    assert server.sent[0]["metadata"]["requiredEffort"] == "xhigh"
    binding = store.one("SELECT * FROM sessions WHERE id=?", (parent.id,))
    assert binding["bridge_session_id"] == "chat-dedicated-1"
    assert binding["url"].endswith("/c/chat-dedicated-1")

    restarted = BridgeTransport(Store(tmp_path), http_transport=http)
    recovered = await restarted.create_session("root", COORDINATOR_MODEL, "parent")
    assert recovered.id == parent.id and server.opens == 1
    await restarted.send_message(recovered, prompt, "parent-turn")
    assert len(server.sent) == 1
    await restarted.send_message(recovered, "Second exact prompt", "parent-turn-2")
    assert server.sent[-1]["sessionId"] == "chat-dedicated-1"
    await restarted.await_response(recovered, "parent-turn-2")

    leaf = await restarted.create_session("leaf", PRO_MODEL, "leaf")
    server.current_model = server.models[1]
    await restarted.send_message(leaf, "Independent Pro research prompt", "leaf-turn")
    await restarted.await_response(leaf, "leaf-turn")
    assert server.sent[-1]["metadata"]["requiredModel"] == "model-gpt-6-pro"
    assert server.sent[-1]["model"] == server.sent[-1]["effort"] == ""
    assert server.sent[-1]["sourceClientId"] != server.sent[0]["sourceClientId"]
    replacement = await restarted.rollover_session(recovered.id, "parent-rollover")
    assert replacement.id != recovered.id
    again = await restarted.create_session("root", COORDINATOR_MODEL, "parent")
    assert again.id == replacement.id
    assert store.one("SELECT active FROM sessions WHERE id=?", (recovered.id,))["active"] == 0
    assert all(r.headers["authorization"] == "Bearer local-http-token" for r in server.requests)
    assert "local-http-token" not in (tmp_path / "project.yaml").read_text()


async def test_bridge_model_unavailable_and_unverified_effort_never_dispatch(tmp_path):
    store, server, http = setup(tmp_path)
    bridge = BridgeTransport(store, http_transport=http)
    leaf = await bridge.create_session("leaf", PRO_MODEL, "leaf")
    server.models = server.models[:1]
    with pytest.raises(TransportError, match="MODEL_UNAVAILABLE"):
        await bridge.send_message(leaf, "Exact leaf prompt", "missing-pro")
    assert server.sent == []
    parent = await bridge.create_session("root", COORDINATOR_MODEL, "parent")
    server.current_effort = {"id": "high", "label": "High"}
    with pytest.raises(TransportError, match="Extra High"):
        await bridge.send_message(parent, "Exact parent prompt", "wrong-effort")
    assert server.sent == []
    assert store.one("SELECT status FROM turns WHERE id='wrong-effort'")["status"] == "QUEUED"
    with pytest.raises(TransportError, match="outer whitespace"):
        await bridge.send_message(
            parent, " Do not silently trim this approved prompt. ", "whitespace"
        )
    assert server.sent == []


async def test_current_picker_pro_is_gpt6_plus_pro_and_keeps_exact_effort_proof(tmp_path):
    """Actual observed picker shapes; synthetic HTTP, no model inference."""
    store, server, http = setup(tmp_path)
    gpt6 = {"id": "model-gpt-6", "label": "GPT-6", "checked": True}
    pro = {"id": "effort-pro-pro", "label": "Pro", "checked": True, "observedOnly": True}
    server.models = [gpt6, {"id": "model-gpt-5-6-sol", "label": "GPT-5.6 Sol"}]
    server.current_model = gpt6
    bridge = BridgeTransport(store, http_transport=http)
    leaf = await bridge.create_session("leaf", PRO_MODEL, "current-pro")
    with pytest.raises(TransportError, match="fifth intelligence level"):
        await bridge._selection(leaf)
    assert not server.sent
    server.efforts = [pro]
    server.current_effort = pro
    await bridge.send_message(leaf, "An exact research prompt", "real-pro-shape")
    await bridge.await_response(leaf, "real-pro-shape")
    assert server.sent[-1]["metadata"] == {
        "researchNodeId": "leaf",
        "requiredModel": "model-gpt-6",
        "requiredEffort": "effort-pro-pro",
    }
    assert server.sent[-1]["model"] == server.sent[-1]["effort"] == ""
    # A selected Pro level on another model family cannot pass as GPT-6 Pro.
    other = await bridge.create_session("other", PRO_MODEL, "wrong-family")
    server.current_model = server.models[1]
    with pytest.raises(TransportError, match="select exactly GPT-6 Pro"):
        await bridge.send_message(other, "An exact research prompt", "wrong-family")
    # The production coordinator default is the same current GPT-6 family,
    # but it requires Extra High rather than the Pro tier.
    server.current_model = gpt6
    parent = await bridge.create_session("root", COORDINATOR_MODEL, "current-parent")
    with pytest.raises(TransportError, match="Extra High"):
        await bridge._selection(parent)
    server.efforts = [{"id": "xhigh", "label": "Extra High"}]
    server.current_effort = server.efforts[0]
    await bridge._selection(parent)
    assert len(server.sent) == 1
    # Changing intelligence after a Pro Send never accepts the completed text.
    server.efforts = [pro]
    server.current_effort = pro
    await bridge.send_message(leaf, "A second exact research prompt", "changed-pro-tier")
    server.current_effort = {"id": "xhigh", "label": "Extra High"}
    with pytest.raises(TransportError, match="MODEL_UNVERIFIED"):
        await bridge.await_response(leaf, "changed-pro-tier")
    assert len(server.sent) == 2
    assert (
        store.one("SELECT raw_response FROM turns WHERE id='changed-pro-tier'")["raw_response"]
        is None
    )


async def test_bridge_lost_ack_and_restart_reconcile_pending_without_duplicate_send(tmp_path):
    store, server, http = setup(tmp_path)
    bridge = BridgeTransport(store, http_transport=http)
    session = await bridge.create_session("root", COORDINATOR_MODEL, "parent")
    server.lose_ack = True
    with pytest.raises(TransportError):
        await bridge.send_message(session, "Exact pending parent prompt", "pending")
    assert store.one("SELECT status FROM turns WHERE id='pending'")["status"] == "UNCERTAIN"
    restarted = BridgeTransport(Store(tmp_path), http_transport=http)
    await restarted.send_message(session, "Exact pending parent prompt", "pending")
    response = await restarted.await_response(session, "pending")
    assert "Complete English answer" in response
    assert len(server.sent) == 1
    assert store.one("SELECT status FROM turns WHERE id='pending'")["status"] == "COMPLETED"


async def test_bridge_unknown_delivery_stays_uncertain_and_terminal_error_is_not_a_reply(tmp_path):
    store, server, http = setup(tmp_path)
    bridge = BridgeTransport(store, http_transport=http)
    session = await bridge.create_session("root", COORDINATOR_MODEL, "parent")
    server.lose_ack = server.discard_dispatch = True
    with pytest.raises(TransportError):
        await bridge.send_message(session, "Exact uncertain prompt", "uncertain")
    restarted = BridgeTransport(Store(tmp_path), http_transport=http)
    for _ in range(2):
        with pytest.raises(TransportError, match="UNCERTAIN"):
            await restarted.await_response(session, "uncertain")
    assert len(server.sent) == 1
    local = store.one("SELECT * FROM turns WHERE id='uncertain'")
    assert local["status"] == "UNCERTAIN" and local["raw_response"] is None

    # Only the durable terminal error is authoritative, never a preview.
    body = server.sent[0]
    server.turns[body["id"]] = {
        "id": body["id"],
        "input": {k: v for k, v in body.items() if k != "id"},
        "status": "failed",
        "error": {"code": "MODEL_UNAVAILABLE", "message": "Model disappeared"},
    }
    with pytest.raises(TransportError, match="MODEL_UNAVAILABLE"):
        await restarted.await_response(session, "uncertain")
    assert local["raw_response"] is None and len(server.sent) == 1


async def test_bridge_changed_effort_preserves_completed_attempt_without_accepting_or_resending(
    tmp_path,
):
    store, server, http = setup(tmp_path)
    bridge = BridgeTransport(store, http_transport=http)
    session = await bridge.create_session("root", COORDINATOR_MODEL, "parent")
    await bridge.send_message(session, "Exact Extra High parent prompt", "selection-changed")
    server.complete(server.sent[0]["id"])
    server.current_effort = {"id": "high", "label": "High", "value": "high"}
    with pytest.raises(TransportError, match="MODEL_UNVERIFIED"):
        await bridge.await_response(session, "selection-changed")
    local = store.one("SELECT * FROM turns WHERE id='selection-changed'")
    assert local["status"] == "UNCERTAIN" and local["raw_response"] is None
    saved = store.one("SELECT payload FROM events WHERE type='bridge_terminal_observed'")
    assert "Complete English answer" in saved["payload"]
    server.current_effort = {"id": "xhigh", "label": "Extra High", "value": "xhigh"}
    restarted = BridgeTransport(Store(tmp_path), http_transport=http)
    requests_before = len(server.requests)
    with pytest.raises(TransportError, match="MODEL_UNVERIFIED"):
        await restarted.await_response(session, "selection-changed")
    assert len(server.requests) == requests_before
    assert len(server.sent) == 1
    # Only an explicit operator confirmation/paste through manual relay resolves
    # the held attempt; merely changing the current UI selection cannot do so.
    observed = json.loads(saved["payload"])["response"]
    manual = ManualRelayTransport(store)
    manual.bind_session(session.id, observed["session"]["url"], COORDINATOR_MODEL)
    manual.submit_response("selection-changed", observed["answer"])
    assert await restarted.await_response(session, "selection-changed") == observed["answer"]
    assert len(server.sent) == 1


async def test_bridge_explicit_undelivered_acknowledgement_preserves_failure_and_rejects_delivery(
    tmp_path,
):
    store, server, http = setup(tmp_path)
    bridge = BridgeTransport(store, http_transport=http)
    session = await bridge.create_session("root", COORDINATOR_MODEL, "parent")
    await bridge.send_message(session, "Exact busy-rejected prompt", "busy")
    request_id = server.sent[0]["id"]
    message = "Browser extension client dedicated-1 is busy with another local request."
    turn = server.turns[request_id]
    turn.update(status="failed", output=None, error={"code": "failed", "message": message})
    events = [
        {"type": "turn/queued", "data": {"turnId": request_id}},
        {"type": "turn/started", "data": {"turnId": request_id}},
        {"type": "request.started", "data": {"requestId": request_id}},
        {
            "type": "request.error",
            "data": {"requestId": request_id, "code": "failed", "message": message},
        },
        {"type": "turn/failed", "data": {"turn": turn}},
    ]
    server.turn_events[request_id] = events
    with pytest.raises(TransportError, match="busy"):
        await bridge.await_response(session, "busy")
    with pytest.raises(TransportError, match="another unresolved turn"):
        await bridge.send_message(session, "A separately authorized new prompt", "new-turn")
    assert len(server.sent) == 1
    server.turn_events[request_id] = (
        events[:-1]
        + [{"type": "prompt.delivered", "data": {"requestId": request_id}}]
        + events[-1:]
    )
    with pytest.raises(TransportError, match="delivered Bridge turn evidence"):
        await bridge.acknowledge_undelivered_failure(session, "busy")
    server.turn_events[request_id] = events
    turn["error"]["message"] = "Ambiguous browser failure"
    with pytest.raises(TransportError, match="proven pre-dispatch busy rejection"):
        await bridge.acknowledge_undelivered_failure(session, "busy")
    turn["error"]["message"] = message
    for status in ("SENT", "UNCERTAIN"):
        store.execute("UPDATE turns SET status=? WHERE id='busy'", (status,))
        with pytest.raises(TransportError, match="known terminal error"):
            await bridge.acknowledge_undelivered_failure(session, "busy")
    store.execute("UPDATE turns SET status='ERROR' WHERE id='busy'")
    original = store.one("SELECT * FROM turns WHERE id='busy'")
    result = await bridge.acknowledge_undelivered_failure(session, "busy")
    assert result["status"] == "FAILED_NOT_SENT"
    saved = store.one("SELECT * FROM turns WHERE id='busy'")
    assert saved["raw_response"] is None and saved["error"] == original["error"]
    assert saved["bridge_request_id"] == request_id
    assert store.one("SELECT id FROM events WHERE type='bridge_undelivered_failure_acknowledged'")
    with pytest.raises(TransportError, match="new approved turn identity"):
        await bridge.send_message(session, "Exact busy-rejected prompt", "busy")
    await bridge.send_message(session, "A separately authorized new prompt", "new-turn")
    assert len(server.sent) == 2 and server.sent[-1]["id"] != request_id
    await bridge.await_response(session, "new-turn")


async def test_composer_not_sent_release_requires_positive_source_and_terminal_proof(tmp_path):
    store, server, http = setup(tmp_path)
    bridge = BridgeTransport(store, http_transport=http)
    session = await bridge.create_session("root", COORDINATOR_MODEL, "parent")
    await bridge.send_message(session, "Complete long approved prompt", "composer-failed")
    request_id = server.sent[0]["id"]
    proof = {
        "code": "COMPOSER_TEXT_VERIFY_FAILED",
        "message": "Input preparation refused",
        "provenNotExecuted": True,
        "cancellationEvidence": {
            "source": "composer_preparation",
            "reason": "submission_boundary_not_entered",
        },
    }
    turn = server.turns[request_id]
    turn.update(status="failed", output=None, error=dict(proof))
    source = {**proof, "requestId": request_id, "effectType": "prompt.submit"}
    events = [
        {"type": "turn/queued", "data": {"turnId": request_id}},
        {"type": "prompt.delivered", "data": {"requestId": request_id}},
        {"type": "diagnostic.request.effect.cancelled", "data": {"payload": source}},
        {"type": "turn/failed", "data": {"turn": turn}},
    ]
    server.turn_events[request_id] = events
    with pytest.raises(TransportError, match="COMPOSER_TEXT_VERIFY_FAILED"):
        await bridge.await_response(session, "composer-failed")
    for missing in ("provenNotExecuted", "cancellationEvidence"):
        removed = turn["error"].pop(missing)
        with pytest.raises(TransportError, match="positively prove"):
            await bridge.acknowledge_not_submitted(session, "composer-failed")
        turn["error"][missing] = removed
    source["provenNotExecuted"] = False
    with pytest.raises(TransportError, match="Source cancellation"):
        await bridge.acknowledge_not_submitted(session, "composer-failed")
    source["provenNotExecuted"] = True
    events.insert(
        -1, {"type": "diagnostic.prompt.submit.attempt", "data": {"requestId": request_id}}
    )
    with pytest.raises(TransportError, match="Send attempt"):
        await bridge.acknowledge_not_submitted(session, "composer-failed")
    events.pop(-2)
    original = store.one("SELECT * FROM turns WHERE id='composer-failed'")
    await bridge.acknowledge_not_submitted(session, "composer-failed")
    await bridge.acknowledge_not_submitted(session, "composer-failed")
    saved = store.one("SELECT * FROM turns WHERE id='composer-failed'")
    assert saved["status"] == "FAILED_NOT_SENT" and saved["raw_response"] is None
    assert saved["error"] == original["error"] and saved["bridge_request_id"] == request_id
    assert (
        len(store.query("SELECT id FROM events WHERE type='bridge_not_submitted_acknowledged'"))
        == 1
    )
    with pytest.raises(TransportError, match="new approved turn identity"):
        await bridge.send_message(session, "Complete long approved prompt", "composer-failed")
    assert len(server.sent) == 1


async def test_busy_ack_exact_recovered_blocker_preserves_both_originals(tmp_path):
    from math_research_agent.store import digest, encode

    store, server, http = setup(tmp_path)
    task = "Prove the sharp cyclic inequality for each integer N at least three, including exact equality conditions and boundary checks."
    child = store.split(
        "root", [{"goal": "Audit cyclic equality", "relative_weight": 1, "initial_prompt": task}]
    )[0]
    bridge = BridgeTransport(store, http_transport=http)
    session = await bridge.create_session(child, PRO_MODEL, "leaf")
    server.current_model = server.models[1]
    client = server.clients[-1]
    client.update(url="https://chatgpt.com/c/old-conversation", session={"id": "old-conversation"})
    store.execute(
        "UPDATE sessions SET bridge_session_id='old-conversation',url=? WHERE id=?",
        (client["url"], session.id),
    )
    round_ = store.one("SELECT * FROM rounds WHERE node_id=?", (child,))
    old_id, old_request = "leaf:" + round_["id"] + ":e0:a0", "mathagent_" + "a" * 32
    store.execute(
        "INSERT INTO turns(id,session_id,prompt,status,error,bridge_request_id) VALUES(?,?,?,'ERROR','original canonical failure',?)",
        (old_id, session.id, task, old_request),
    )
    report = encode({"node_id": child, "round_id": round_["id"], "evidence": "Fixture proof"})
    store.execute("UPDATE rounds SET report=? WHERE id=?", (report, round_["id"]))
    original = store.one("SELECT * FROM turns WHERE id=?", (old_id,))
    receipt = {
        "turn_id": old_id,
        "original_turn_hash": digest(encode(original)),
        "request_id": old_request,
        "session_id": session.id,
        "round_id": round_["id"],
        "node_id": child,
        "parent_id": "root",
        "conversation_id": "old-conversation",
        "report_sha256": digest(report),
        "terminal_evidence": {"submission_authority": "AUTHENTICATED_NETWORK_USER_AND_FINAL_TEXT"},
    }
    store.event("leaf_recovery_committed", receipt)
    await bridge.send_message(session, "Separately approved new prompt", "new-busy")
    request_id = server.sent[0]["id"]
    message = f"Browser extension client {client['id']} is busy with {old_request}."
    turn = server.turns[request_id]
    turn.update(status="failed", output=None, error={"code": "failed", "message": message})
    events = [
        {"type": "turn/queued", "data": {"turnId": request_id}},
        {"type": "turn/started", "data": {"turnId": request_id}},
        {"type": "request.started", "data": {"requestId": request_id}},
        {
            "type": "request.error",
            "data": {"requestId": request_id, "code": "failed", "message": message},
        },
        {"type": "turn/failed", "data": {"turn": turn}},
    ]
    server.turn_events[request_id] = events
    with pytest.raises(TransportError, match="busy"):
        await bridge.await_response(session, "new-busy")
    busy_original = store.one("SELECT * FROM turns WHERE id='new-busy'")
    with pytest.raises(TransportError, match="proven pre-dispatch"):
        await bridge.acknowledge_undelivered_failure(session, "new-busy")
    with pytest.raises(TransportError, match="committed source-recovery receipt"):
        await bridge.acknowledge_undelivered_failure(
            session, "new-busy", blocking_request_id="unrelated"
        )
    store.execute("UPDATE turns SET error='changed original' WHERE id=?", (old_id,))
    with pytest.raises(TransportError, match="committed source-recovery receipt"):
        await bridge.acknowledge_undelivered_failure(
            session, "new-busy", blocking_request_id=old_request
        )
    store.execute("UPDATE turns SET error=? WHERE id=?", (original["error"], old_id))
    server.turn_events[request_id] = events[:-1] + [{"type": "prompt.delivered"}] + events[-1:]
    with pytest.raises(TransportError, match="delivered Bridge turn evidence"):
        await bridge.acknowledge_undelivered_failure(
            session, "new-busy", blocking_request_id=old_request
        )
    server.turn_events[request_id] = events
    result = await bridge.acknowledge_undelivered_failure(
        session, "new-busy", blocking_request_id=old_request
    )
    assert result["status"] == "FAILED_NOT_SENT"
    saved = store.one("SELECT * FROM turns WHERE id='new-busy'")
    assert {k: v for k, v in saved.items() if k != "status"} == {
        k: v for k, v in busy_original.items() if k != "status"
    }
    assert store.one("SELECT * FROM turns WHERE id=?", (old_id,)) == original
    assert store.query("SELECT payload FROM events WHERE type='leaf_recovery_committed'") == [
        {"payload": encode(receipt)}
    ]
    assert len(server.sent) == 1
