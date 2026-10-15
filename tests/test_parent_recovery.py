"""Synthetic recovery proofs; these tests make no browser or inference requests."""

import json
from copy import deepcopy

import pytest

from math_research_agent.bridge_transport import BridgeTransport
from math_research_agent.config import Config
from math_research_agent.recovery import (
    commit_parent_recovery,
    unresolved_turns,
    validate_parent_recovery,
)
from math_research_agent.scheduler import Scheduler
from math_research_agent.schemas import PARENT_MODEL
from math_research_agent.store import Store, digest, encode
from math_research_agent.transport import ManualRelayTransport, ScriptedTransport, TransportError

TASK = "Derive the addition identity with explicit index conventions, prove every algebraic step, and check the zero-index boundary."


async def fixture(tmp_path):
    store = Store.initialize(
        tmp_path,
        "Investigate Fibonacci index identities.",
        Config(transport="fake", max_active_leaves=2),
    )
    children = store.split(
        "root",
        [
            {"goal": goal, "relative_weight": 0.5, "initial_prompt": TASK}
            for goal in ["Prove the addition identity.", "Audit zero-index conventions."]
        ],
    )
    scheduler = Scheduler(store, ScriptedTransport(store))
    for node_id in children:
        round_ = store.one("SELECT * FROM rounds WHERE node_id=?", (node_id,))
        await scheduler._leaf(round_["id"])
    session = await scheduler._session("root", PARENT_MODEL)
    store.execute(
        "UPDATE sessions SET bridge_client_id='extension:tab:7',bridge_session_id='conversation',bridge_model='model-gpt-6',bridge_effort='xhigh',url='https://chatgpt.com/c/conversation' WHERE id=?",
        (session.id,),
    )
    round_ = store.one("SELECT * FROM rounds WHERE node_id=?", (children[0],))
    turn_id = "parent:" + round_["id"] + ":e0:a0"
    prompt = "Exact synthetic Parent input with full mathematical evidence.\n" + TASK
    store.execute(
        "INSERT INTO turns(id,session_id,prompt,status,error,bridge_request_id) VALUES(?,?,?,'ERROR','CANONICAL_RECOVERY_UNCERTAIN','known-request')",
        (turn_id, session.id, prompt),
    )
    answer = encode(
        {
            "child_node_id": children[0],
            "responding_to_round_id": round_["id"],
            "assessment": "The synthetic report needs a complete independent boundary verification.",
            "next_prompt": TASK,
        }
    )
    proof = {
        "upstream": {
            "id": "known-request",
            "status": "failed",
            "error": {"code": "CANONICAL_RECOVERY_UNCERTAIN"},
            "output": None,
            "input": {
                "message": prompt,
                "sessionId": "conversation",
                "sourceClientId": "extension:tab:7",
                "metadata": {
                    "researchNodeId": "root",
                    "requiredModel": "model-gpt-6",
                    "requiredEffort": "xhigh",
                },
            },
        },
        "events": [
            {
                "type": "diagnostic.chat.prompt.submit.confirmed",
                "data": {
                    "requestId": "known-request",
                    "clientId": "extension:tab:7",
                    "payload": {
                        "requestId": "known-request",
                        "url": "https://chatgpt.com/c/conversation",
                        "turnKey": "user-message::user",
                        "fullPromptTextMatch": True,
                        "expectedSha256": digest(prompt),
                        "observedSha256": digest(prompt),
                        "expectedCharacters": len(prompt),
                        "observedCharacters": len(prompt),
                    },
                },
            }
        ],
        "observation": {
            "requestId": "known-request",
            "url": "https://chatgpt.com/c/conversation",
            "userTurnKey": "user-message",
            "exactRenderedUserText": prompt,
            "assistantMessageId": "assistant-message",
            "assistantCandidate": answer,
        },
        "recovered": {
            "answer": answer,
            "sourceClientId": "extension:tab:7",
            "session": {"id": "conversation"},
            "url": "https://chatgpt.com/c/conversation",
            "reconciliation": {
                "source": "conversation-record",
                "version": 1,
                "status": "matched_complete",
                "reason": "exact_branch_boundary",
                "conversationId": "conversation",
                "userMessageId": "user-message",
                "assistantMessageId": "assistant-message",
                "backendStatus": "finished_successfully",
                "endTurn": True,
                "textMatches": True,
            },
        },
    }
    return scheduler, turn_id, proof, children


def authenticated_history(proof):
    answer = proof["observation"]["assistantCandidate"]
    record = {
        "conversation_id": "conversation",
        "current_node": "assistant",
        "mapping": {
            "root": {"parent": None, "message": None},
            "user": {
                "parent": "root",
                "message": {
                    "id": "user-message",
                    "author": {"role": "user"},
                    "content": {
                        "content_type": "text",
                        "parts": [proof["upstream"]["input"]["message"]],
                    },
                    "metadata": {"request_id": "native-request"},
                },
            },
            "assistant": {
                "parent": "user",
                "message": {
                    "id": "assistant-message",
                    "author": {"role": "assistant"},
                    "status": "finished_successfully",
                    "end_turn": True,
                    "channel": "final",
                    "recipient": "all",
                    "content": {
                        "content_type": "text",
                        "parts": ["<escape>" + answer + "</escape>"],
                    },
                    "metadata": {
                        "model_slug": "gpt-6-thinking",
                        "resolved_model_slug": "gpt-6-thinking",
                        "thinking_effort": "max",
                        "is_complete": True,
                        "finish_details": {"type": "stop"},
                        "request_id": "native-request",
                        "model_dil_v2": {"constants": {"0": answer}},
                    },
                },
            },
        },
    }
    return {
        "source": "ACTUAL_OWN_TAB_NETWORK_RESPONSE",
        "tabId": "7",
        "conversationUrl": "https://chatgpt.com/c/conversation",
        "requestId": "network-request",
        "url": "https://chatgpt.com/backend-api/conversation/conversation",
        "status": 200,
        "body": {"base64Encoded": False, "body": encode(record)},
    }


async def test_parent_recovery_refuses_adjacent_or_incomplete_evidence(tmp_path):
    scheduler, turn_id, proof, _ = await fixture(tmp_path)
    store = scheduler.store
    before = {
        name: store.query("SELECT * FROM " + name)
        for name in ("turns", "rounds", "parent_responses", "events")
    }
    changes = [
        (("events", 0, "data", "payload", "observedSha256"), "wrong"),
        (("observation", "userTurnKey"), "another-user"),
        (("observation", "assistantMessageId"), "adjacent-assistant"),
        (("recovered", "session", "id"), "another-conversation"),
        (("recovered", "reconciliation", "status"), "matched_incomplete"),
        (("recovered", "reconciliation", "backendStatus"), "in_progress"),
        (("recovered", "reconciliation", "endTurn"), False),
        (("recovered", "reconciliation", "textMatches"), False),
        (
            ("observation", "assistantCandidate"),
            proof["observation"]["assistantCandidate"].replace(
                "synthetic report", "modified report"
            ),
        ),
    ]
    for path, value in changes:
        wrong = deepcopy(proof)
        target = wrong
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        with pytest.raises(ValueError, match="recovery refused"):
            validate_parent_recovery(store, turn_id, wrong)
        assert {name: store.query("SELECT * FROM " + name) for name in before} == before
        assert [row["id"] for row in unresolved_turns(store)] == [turn_id]
    for field, value in (
        ("id", "unrelated-assistant"),
        ("status", "in_progress"),
        ("end_turn", False),
    ):
        wrong = deepcopy(proof)
        wrong["authenticated_history"] = authenticated_history(proof)
        record = json.loads(wrong["authenticated_history"]["body"]["body"])
        record["mapping"]["assistant"]["message"][field] = value
        wrong["authenticated_history"]["body"]["body"] = encode(record)
        with pytest.raises(ValueError, match="network history"):
            validate_parent_recovery(store, turn_id, wrong)
        assert {name: store.query("SELECT * FROM " + name) for name in before} == before
    await scheduler.aclose()


@pytest.mark.parametrize("unconfirmed", [False, True])
async def test_parent_recovery_is_idempotent_keeps_failed_source_and_other_p0(
    tmp_path, unconfirmed
):
    scheduler, turn_id, proof, children = await fixture(tmp_path)
    store = scheduler.store
    original = store.one("SELECT * FROM turns WHERE id=?", (turn_id,))
    # Only JSON formatting may differ; every original string and TeX value stays exact.
    proof["recovered"]["answer"] = json.dumps(json.loads(proof["recovered"]["answer"]), indent=3)
    proof["authenticated_history"] = authenticated_history(proof)
    proof["recovered"]["reconciliation"] = {"status": "unavailable", "reason": "http_404"}
    if unconfirmed:
        store.execute("UPDATE turns SET error='CANONICAL_DEADLINE_EXCEEDED' WHERE id=?", (turn_id,))
        original = store.one("SELECT * FROM turns WHERE id=?", (turn_id,))
        proof["upstream"]["error"]["code"] = "CANONICAL_DEADLINE_EXCEEDED"
        proof["upstream"]["completedAt"] = "2026-10-15T09:09:21.425Z"

        def event(name, payload):
            return {
                "type": name,
                "data": {
                    "requestId": "known-request",
                    "clientId": "extension:tab:7",
                    "payload": payload,
                },
            }

        proof["events"] = [
            {
                "type": "request.effect.started",
                "data": {
                    "requestId": "known-request",
                    "effectType": "prompt.submit",
                    "effectId": "known-request:prompt.submit:attempt:1",
                },
            },
            event(
                "diagnostic.composer.text_verified",
                {
                    "verification": "full_text_equal",
                    "length": len(original["prompt"]),
                    "sendReady": True,
                },
            ),
            event("diagnostic.send_button.found", {"attempt": 1, "kind": "prompt"}),
            event("diagnostic.prompt.turn_boundary.armed", {"turnCount": 2, "baselineCount": 2}),
            event(
                "diagnostic.prompt.user_turn_text_mismatch",
                {
                    "candidates": [
                        {
                            "key": "user-message::user",
                            "index": 2,
                            "textLength": len(original["prompt"]) - 8,
                        }
                    ]
                },
            ),
        ]
        record = json.loads(proof["authenticated_history"]["body"]["body"])
        record["mapping"]["assistant"]["message"]["content"]["parts"] = [
            '<CodeBlock language="json" editable={false}>\n'
            + proof["observation"]["assistantCandidate"]
            + "\n</CodeBlock>"
        ]
        proof["authenticated_history"]["body"]["body"] = encode(record)
        proof["observation"]["exactRenderedUserText"] = "The renderer shortened this user message."
        proof["observation"]["dom"] = [
            {
                "html": '<div data-chatgpt-search-message-ids="assistant-message assistant-message" data-chatgpt-selection-conversation-id="conversation">'
            }
        ]
        proof["recovered"]["answer"] = "```json\n" + proof["recovered"]["answer"] + "\n```"
        before = {
            name: store.query("SELECT * FROM " + name)
            for name in ("turns", "rounds", "parent_responses", "events")
        }
        for change in ("candidate", "backend_user"):
            wrong = deepcopy(proof)
            if change == "candidate":
                wrong["events"][-1]["data"]["payload"]["candidates"][0]["key"] = (
                    "adjacent-user::user"
                )
            else:
                record = json.loads(wrong["authenticated_history"]["body"]["body"])
                record["mapping"]["user"]["message"]["content"]["parts"] = [
                    "Truncated backend input"
                ]
                wrong["authenticated_history"]["body"]["body"] = encode(record)
            with pytest.raises(ValueError, match="recovery refused"):
                validate_parent_recovery(store, turn_id, wrong)
            assert {name: store.query("SELECT * FROM " + name) for name in before} == before
    receipt = commit_parent_recovery(scheduler, turn_id, proof)
    assert not receipt["idempotent"]
    assert receipt["terminal_evidence"]["source"] == "ACTUAL_OWN_TAB_NETWORK_RESPONSE"
    if unconfirmed:
        assert receipt["terminal_evidence"]["confirmed_send_diagnostic"] is False
        assert receipt["terminal_evidence"]["user_sha256"] == digest(original["prompt"])
    assert proof["recovered"]["reconciliation"]["status"] == "unavailable"
    assert commit_parent_recovery(scheduler, turn_id, proof)["idempotent"]
    assert store.one("SELECT * FROM turns WHERE id=?", (turn_id,)) == original
    assert not unresolved_turns(store)
    assert not ManualRelayTransport(store).list_pending()

    class ChangedTabBridge(BridgeTransport):
        async def _json(self, method, path, **kwargs):
            assert (method, path) == ("GET", "/browser/clients")
            return {
                "clients": [
                    {
                        "id": "extension:tab:7",
                        "ready": True,
                        "url": "https://chatgpt.com/c/unrelated",
                    }
                ]
            }

    bridge = ChangedTabBridge(store)
    with pytest.raises(TransportError, match="moved to another conversation"):
        await bridge._binding(bridge.get_session(original["session_id"]))
    assert len(store.query("SELECT * FROM parent_responses")) == 1
    assert len(store.query("SELECT * FROM events WHERE type='parent_recovery_committed'")) == 1
    next_round = store.one("SELECT * FROM rounds WHERE id=?", (receipt["next_round_id"],))
    assert next_round["stage"] == "PROMPT_READY" and next_round["task"] == TASK
    assert not store.one(
        "SELECT id FROM turns WHERE id LIKE ?", ("leaf:" + next_round["id"] + ":%",)
    )
    sibling_round = store.one("SELECT * FROM rounds WHERE node_id=?", (children[1],))
    assert sibling_round["stage"] == "AWAITING_PARENT_RESPONSE"
    # Another mandatory assessment can now use the same Parent, without resending the old turn.
    await scheduler._parent(sibling_round["id"])
    assert len(store.query("SELECT * FROM parent_responses")) == 2
    assert store.one("SELECT * FROM turns WHERE id=?", (turn_id,)) == original
    assert not any(call["turn_id"] == turn_id for call in scheduler.transport.sent)
    parent = store.one("SELECT * FROM parent_responses WHERE round_id=?", (receipt["round_id"],))
    store.execute(
        "UPDATE parent_responses SET payload=? WHERE round_id=?",
        (parent["payload"] + " ", receipt["round_id"]),
    )
    assert [row["id"] for row in unresolved_turns(store)] == [
        turn_id
    ]  # Receipt cannot cover changed evidence.
    await scheduler.aclose()
