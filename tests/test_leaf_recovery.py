"""Synthetic source proofs only; no browser or inference requests."""

import html
import json
import string
from copy import deepcopy

import pytest

from math_research_agent.config import Config
from math_research_agent.leaf_recovery import commit_leaf_recovery, validate_leaf_recovery
from math_research_agent.recovery import unresolved_turns
from math_research_agent.scheduler import Scheduler
from math_research_agent.schemas import PRO_MODEL
from math_research_agent.store import Store, digest, encode
from math_research_agent.transport import ScriptedTransport


@pytest.mark.parametrize("review", [False, True])
@pytest.mark.parametrize("failed_first", [False, True])
async def test_leaf_recovery_preserves_invalid_terminal_and_normal_report_gate(
    tmp_path, review, failed_first
):
    store = Store.initialize(
        tmp_path, "Prove cyclic finite-sum identities.", Config(transport="fake")
    )
    node = store.split(
        "root",
        [
            {
                "goal": "Prove a sharp finite-sum identity.",
                "relative_weight": 1,
                "initial_prompt": "Prove the cyclic finite sum identity with exact indexing and explicit boundary cases for every integer size.",
            }
        ],
    )[0]
    scheduler = Scheduler(store, ScriptedTransport(store))
    session = await scheduler._session(node, PRO_MODEL)
    store.execute(
        "UPDATE sessions SET bridge_client_id='extension:tab:7',bridge_session_id='conversation',bridge_model='model-gpt-6',bridge_effort='effort-pro-pro',url='https://chatgpt.com/c/conversation' WHERE id=?",
        (session.id,),
    )
    round_ = store.one("SELECT * FROM rounds WHERE node_id=?", (node,))
    store.execute("UPDATE rounds SET stage='SOLVING' WHERE id=?", (round_["id"],))
    scheduler.set_review_mode(review)
    turn_id = "leaf:" + round_["id"] + ":e0:a0"
    raw = "Worked for 5m 59s"
    store.execute(
        "INSERT INTO turns(id,session_id,prompt,raw_response,status,error,bridge_request_id) VALUES(?,?,?,?,'INVALID','json_invalid','known-request')",
        (turn_id, session.id, round_["prompt"], raw),
    )
    original = store.one("SELECT * FROM turns WHERE id=?", (turn_id,))
    answer = encode(
        {
            "node_id": node,
            "round_id": round_["id"],
            "status": "PARTIAL",
            "summary": "Synthetic exact finite-sum identity.",
            "findings": ["The boundary identity holds."],
            "evidence": "Sum s_{j+1} and \\sin(theta) exactly; preserve every underscore.",
            "obstacles": ["Sharpness needs a separate proof."],
            "recommended_next_steps": ["Audit the equality case."],
            "split_suggestion": [],
            "important_update": True,
        }
    )
    exchange = {"turn_exchange_id": "exchange", "working_turn_id": "exchange"}
    messages = [
        {
            "id": "user-message",
            "author": {"role": "user"},
            "content": {"content_type": "text", "parts": [round_["prompt"]]},
            "metadata": {**exchange, "request_id": "native-user"},
        },
        {
            "id": "recap",
            "author": {"role": "assistant"},
            "content": {"content_type": "reasoning_recap"},
            "end_turn": True,
            "metadata": exchange,
        },
        {
            "id": "assistant-message",
            "author": {"role": "assistant"},
            "status": "finished_successfully",
            "end_turn": True,
            "recipient": "all",
            "channel": "final",
            "content": {"content_type": "text", "parts": [answer]},
            "metadata": {
                **exchange,
                "request_id": "different-async-final",
                "async_source": "provider:native-user",
                "model_slug": "gpt-6-pro",
                "resolved_model_slug": "gpt-6-pro",
                "default_model_slug": "gpt-6-pro",
            },
        },
    ]
    history = {
        "conversation_id": "conversation",
        "current_node": "assistant-message",
        "default_model_slug": "gpt-6-pro",
        "messages": messages,
        "page_info": {
            "start_cursor": "user-message",
            "end_cursor": "assistant-message",
            "has_previous_page": False,
            "has_next_page": False,
        },
    }
    proof = {
        "upstream": {
            "id": "known-request",
            "status": "completed",
            "completedAt": "2026-10-15T08:11:16Z",
            "error": None,
            "input": {
                "message": round_["prompt"],
                "sessionId": "",
                "sourceClientId": "extension:tab:7",
                "metadata": {
                    "researchNodeId": node,
                    "requiredModel": "model-gpt-6",
                    "requiredEffort": "effort-pro-pro",
                },
            },
            "output": {
                "answer": raw,
                "response": {
                    "requestId": "known-request",
                    "answer": raw,
                    "session": {"id": "conversation"},
                    "sourceClientId": "extension:tab:7",
                    "url": "https://chatgpt.com/c/conversation",
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
                        "confirmed": True,
                        "fullPromptTextMatch": True,
                        "expectedSha256": digest(round_["prompt"]),
                        "observedSha256": digest(round_["prompt"]),
                        "expectedCharacters": len(round_["prompt"]),
                        "observedCharacters": len(round_["prompt"]),
                        "url": "https://chatgpt.com/c/local-chatgpt%3Anew",
                        "turnKey": "user-message::user",
                    },
                },
            }
        ],
        "observation": {
            "requestId": "known-request",
            "tabId": 7,
            "url": "https://chatgpt.com/c/conversation",
            "dom": [
                {
                    "html": '<div data-chatgpt-search-message-ids="assistant-message assistant-message" data-chatgpt-selection-conversation-id="conversation">',
                    "text": "Rendered DOM is deliberately not the mathematical content authority.",
                }
            ],
        },
        "authenticated_history": {
            "tabId": 7,
            "route": {
                "requestId": "observed-network",
                "status": 200,
                "url": "https://chatgpt.com/backend-api/conversations/conversation?num_turns=10&include_has_versions=true",
            },
            "response": {"base64Encoded": False, "body": encode(history)},
        },
    }
    if failed_first:
        store.execute(
            "UPDATE sessions SET bridge_session_id=NULL,url=NULL WHERE id=?", (session.id,)
        )
        store.execute(
            "UPDATE turns SET status='ERROR',raw_response=NULL,error='CANONICAL_CONVERSATION_CHANGED' WHERE id=?",
            (turn_id,),
        )
        original = store.one("SELECT * FROM turns WHERE id=?", (turn_id,))
        proof["upstream"].update(
            status="failed", output=None, error={"code": "CANONICAL_CONVERSATION_CHANGED"}
        )

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
                    "length": len(round_["prompt"]),
                    "sendReady": True,
                },
            ),
            event("diagnostic.send_button.found", {"attempt": 1, "kind": "prompt"}),
            event("diagnostic.prompt.turn_boundary.armed", {"turnCount": 0, "baselineCount": 0}),
            event(
                "diagnostic.prompt.user_turn_text_mismatch",
                {
                    "candidates": [
                        {
                            "key": "user-message::user",
                            "index": 0,
                            "textLength": len(round_["prompt"]) - 2,
                        }
                    ]
                },
            ),
        ]
        history["messages"][-1]["content"]["parts"] = ["```json\n" + answer + "\n```"]
        proof["authenticated_history"]["response"]["body"] = encode(history)
    before = {
        name: store.query("SELECT * FROM " + name)
        for name in ("turns", "rounds", "events", "approvals", "sessions")
    }
    for changed in ("exchange", "status", "model", "page", "current", "user", "node"):
        wrong = deepcopy(proof)
        record = json.loads(wrong["authenticated_history"]["response"]["body"])
        if changed == "exchange":
            record["messages"][-1]["metadata"]["working_turn_id"] = "other"
        elif changed == "status":
            record["messages"][-1]["end_turn"] = False
        elif changed == "model":
            record["messages"][-1]["metadata"]["resolved_model_slug"] = "gpt-6-thinking"
        elif changed == "page":
            record["page_info"]["has_next_page"] = True
        elif changed == "current":
            record["current_node"] = "recap"
        elif changed == "user":
            record["messages"][0]["content"]["parts"] = ["Truncated submitted prompt"]
        else:
            record["messages"][-1]["content"]["parts"] = [answer.replace(node, "wrong-node")]
        wrong["authenticated_history"]["response"]["body"] = encode(record)
        with pytest.raises(ValueError, match="recovery refused"):
            validate_leaf_recovery(store, turn_id, wrong)
        assert {name: store.query("SELECT * FROM " + name) for name in before} == before
    if failed_first:
        wrong = deepcopy(proof)
        wrong["events"][-1]["data"]["payload"]["candidates"][0]["key"] = "adjacent-user::user"
        with pytest.raises(ValueError, match="recovery refused"):
            validate_leaf_recovery(store, turn_id, wrong)
        assert {name: store.query("SELECT * FROM " + name) for name in before} == before
        assert [turn["id"] for turn in unresolved_turns(store)] == [turn_id]
    receipt = commit_leaf_recovery(scheduler, turn_id, proof)
    assert not receipt["idempotent"]
    assert commit_leaf_recovery(scheduler, turn_id, proof)["idempotent"]
    assert store.one("SELECT * FROM turns WHERE id=?", (turn_id,)) == original
    assert not unresolved_turns(store)
    if failed_first:
        # A receipt releases only its exact report/source, never arbitrary ERROR rows.
        store.execute("UPDATE rounds SET report=report||' ' WHERE id=?", (round_["id"],))
        assert [turn["id"] for turn in unresolved_turns(store)] == [turn_id]
        store.execute("UPDATE rounds SET report=? WHERE id=?", (answer, round_["id"]))
        assert not unresolved_turns(store)
    assert (
        store.one("SELECT bridge_session_id FROM sessions WHERE id=?", (session.id,))[
            "bridge_session_id"
        ]
        == "conversation"
    )
    saved = store.one("SELECT * FROM rounds WHERE id=?", (round_["id"],))
    assert saved["report"] == answer
    assert saved["report_accepted"] == int(not review)
    assert saved["stage"] == ("REPORT_APPROVAL" if review else "AWAITING_PARENT_RESPONSE")
    approval = store.one(
        "SELECT * FROM approvals WHERE round_id=? AND artifact_type='report'", (round_["id"],)
    )
    assert approval["status"] == ("PENDING" if review else "AUTO_APPROVED")
    assert approval["content_hash"] == digest(answer)
    assert not store.query("SELECT * FROM parent_responses")
    assert len(store.query("SELECT * FROM rounds")) == 1
    assert len(store.query("SELECT * FROM turns")) == 1
    assert (
        json.loads(store.node(node)["research_state"])["evidence"] == json.loads(answer)["evidence"]
    )
    if not review:
        await scheduler._parent(round_["id"])
        assert store.one("SELECT * FROM parent_responses WHERE round_id=?", (round_["id"],))
        assert store.one("SELECT * FROM turns WHERE id=?", (turn_id,)) == original
    # A proven historical commit stays idempotent after the conversation advances.
    store.execute(
        "INSERT INTO turns(id,session_id,prompt,raw_response,status) VALUES('later-local-turn',?,?,?,'COMPLETED')",
        (session.id, "A later synthetic turn in this same conversation.", "A later reply."),
    )
    after_progress = {
        name: store.query("SELECT * FROM " + name)
        for name in ("turns", "rounds", "parent_responses", "approvals", "events", "nodes")
    }
    assert commit_leaf_recovery(scheduler, turn_id, proof)["idempotent"]
    changed_proof = deepcopy(proof)
    changed_proof["upstream"]["id"] = "different-request"
    with pytest.raises(ValueError, match="committed receipt/source/report changed"):
        commit_leaf_recovery(scheduler, turn_id, changed_proof)
    assert {name: store.query("SELECT * FROM " + name) for name in after_progress} == after_progress
    await scheduler.aclose()


async def test_later_pro_recovery_requires_reversible_serialization_and_current_exchange(tmp_path):
    store = Store.initialize(
        tmp_path, "Investigate exact cyclic identities.", Config(transport="fake")
    )
    node = store.split(
        "root",
        [
            {
                "goal": "Check literal mathematical notation.",
                "relative_weight": 1,
                "initial_prompt": "Prove the finite sum identity with exact indexing and check every boundary convention before extending the argument.",
            }
        ],
    )[0]
    scheduler = Scheduler(store, ScriptedTransport(store))
    for _ in range(2):
        row = store.one(
            "SELECT * FROM rounds WHERE node_id=? ORDER BY number DESC LIMIT 1", (node,)
        )
        await scheduler._leaf(row["id"])
        await scheduler._parent(row["id"])
    row = store.one("SELECT * FROM rounds WHERE node_id=? AND number=3", (node,))
    session = await scheduler._session(node, PRO_MODEL)
    store.execute(
        "UPDATE sessions SET bridge_client_id='extension:tab:7',bridge_session_id='conversation',bridge_model='model-gpt-6',bridge_effort='effort-pro-pro',url='https://chatgpt.com/c/conversation' WHERE id=?",
        (session.id,),
    )
    store.execute("UPDATE rounds SET stage='SOLVING' WHERE id=?", (row["id"],))
    turn_id = "leaf:" + row["id"] + ":e0:a0"
    store.execute(
        "INSERT INTO turns(id,session_id,prompt,status,error,bridge_request_id,created_at) VALUES(?,?,?,'ERROR','CANONICAL_DEADLINE_EXCEEDED','later-request','2030-01-01')",
        (turn_id, session.id, row["prompt"]),
    )
    original = store.one("SELECT * FROM turns WHERE id=?", (turn_id,))
    prompt = original["prompt"]
    # Synthetic fixed-grammar serialization, not an inference or server-encoder claim.
    raw = "".join(("\\" if ch in string.punctuation + "\n" else "") + ch for ch in prompt)
    rich_html = (
        '<div data-markdown-text-tone="user-message"><p><span>'
        + html.escape(prompt).replace("\n", "</span><br><span>")
        + "</span></p></div>"
    )
    report = {
        "node_id": node,
        "round_id": row["id"],
        "status": "PARTIAL",
        "summary": "Synthetic third-round boundary audit.",
        "findings": [],
        "evidence": "Preserve \\sin(theta)_1 and [x] exactly.",
        "obstacles": [],
        "recommended_next_steps": ["Assess this report before another round."],
        "split_suggestion": [],
        "important_update": True,
    }
    exchange = {"turn_exchange_id": "current-exchange", "working_turn_id": "current-exchange"}
    messages = [
        {"id": f"old-{i}", "author": {"role": "user" if i % 2 == 0 else "assistant"}}
        for i in range(4)
    ]
    messages += [
        {
            "id": "current-user",
            "author": {"role": "user"},
            "content": {"content_type": "text", "parts": [raw]},
            "metadata": {
                **exchange,
                "serialization_metadata": {"render_format": "markdown"},
                "request_id": "native-current",
            },
        },
        {
            "id": "current-final",
            "author": {"role": "assistant"},
            "status": "finished_successfully",
            "end_turn": True,
            "channel": "final",
            "recipient": "all",
            "content": {"content_type": "text", "parts": ["```json\n" + encode(report) + "\n```"]},
            "metadata": {
                **exchange,
                "request_id": "async-final",
                "async_source": "native-current",
                "model_slug": "gpt-6-pro",
                "resolved_model_slug": "gpt-6-pro",
                "default_model_slug": "gpt-6-pro",
            },
        },
    ]
    history = {
        "conversation_id": "conversation",
        "default_model_slug": "gpt-6-pro",
        "current_node": "current-final",
        "messages": messages,
        "page_info": {
            "start_cursor": "old-0",
            "end_cursor": "current-final",
            "has_previous_page": False,
            "has_next_page": False,
        },
    }

    def diagnostic(name, payload):
        return {
            "type": name,
            "data": {
                "requestId": "later-request",
                "clientId": "extension:tab:7",
                "payload": payload,
            },
        }

    proof = {
        "upstream": {
            "id": "later-request",
            "status": "failed",
            "output": None,
            "error": {"code": "CANONICAL_DEADLINE_EXCEEDED"},
            "completedAt": "2026-10-15T09:53:31Z",
            "input": {
                "message": prompt,
                "sessionId": "conversation",
                "sourceClientId": "extension:tab:7",
                "metadata": {
                    "researchNodeId": node,
                    "requiredModel": "model-gpt-6",
                    "requiredEffort": "effort-pro-pro",
                },
            },
        },
        "events": [
            {
                "type": "request.effect.started",
                "data": {
                    "requestId": "later-request",
                    "effectType": "prompt.submit",
                    "effectId": "later-request:prompt.submit:attempt:1",
                },
            },
            diagnostic(
                "diagnostic.composer.text_verified",
                {"verification": "full_text_equal", "length": len(prompt), "sendReady": True},
            ),
            diagnostic("diagnostic.send_button.found", {"attempt": 1, "kind": "prompt"}),
            diagnostic(
                "diagnostic.prompt.turn_boundary.armed", {"turnCount": 4, "baselineCount": 4}
            ),
        ]
        + [
            diagnostic(
                "diagnostic.prompt.user_turn_text_mismatch",
                {"candidates": [{"key": "current-user::user", "index": 4, "textLength": n}]},
            )
            for n in (100, len(prompt) + 11)
        ],
        "authenticated_history": {
            "tabId": 7,
            "route": {
                "status": 200,
                "requestId": "network-current",
                "url": "https://chatgpt.com/backend-api/conversations/conversation?num_turns=10&include_has_versions=true",
            },
            "response": {"base64Encoded": False, "body": encode(history)},
        },
        "observation": {
            "requestId": "later-request",
            "tabId": 7,
            "url": "https://chatgpt.com/c/conversation",
            "dom": [
                {"key": "user-unit", "html": rich_html},
                {
                    "html": '<div data-chatgpt-search-message-ids="current-final current-final" data-chatgpt-selection-conversation-id="conversation">'
                },
            ],
        },
        "rich_user": {
            "key": "user-unit",
            "url": "https://chatgpt.com/c/conversation",
            "html": rich_html,
            "text": prompt,
        },
        "user_identity": {
            "url": "https://chatgpt.com/c/conversation",
            "ancestors": [
                {
                    "attributes": [
                        ["data-chatgpt-search-message-ids", "current-user"],
                        ["data-chatgpt-search-unit-key", "user-unit"],
                    ],
                    "html": rich_html,
                }
            ],
        },
    }
    before = {
        name: store.query("SELECT * FROM " + name)
        for name in ("turns", "rounds", "parent_responses", "events")
    }
    for change in ("candidate", "raw", "exchange", "prior_final", "rich_context", "native_user"):
        wrong = deepcopy(proof)
        record = json.loads(wrong["authenticated_history"]["response"]["body"])
        if change == "candidate":
            wrong["events"][-1]["data"]["payload"]["candidates"][0]["key"] = "other-user::user"
        elif change == "raw":
            record["messages"][-2]["content"]["parts"][0] += "changed mathematical text"
        elif change == "exchange":
            record["messages"][-1]["metadata"]["working_turn_id"] = "prior-exchange"
        elif change == "prior_final":
            record["current_node"] = "old-3"
        elif change == "rich_context":
            wrong["rich_user"]["html"] = "<code>" + rich_html + "</code>"
        else:
            wrong["user_identity"]["ancestors"][0]["attributes"][0][1] = "other-user"
        wrong["authenticated_history"]["response"]["body"] = encode(record)
        with pytest.raises(ValueError, match="recovery refused"):
            validate_leaf_recovery(store, turn_id, wrong)
        assert {name: store.query("SELECT * FROM " + name) for name in before} == before
    result = commit_leaf_recovery(scheduler, turn_id, proof)
    assert (
        result["terminal_evidence"]["submission_authority"]
        == "AUTHENTICATED_SERIALIZED_NETWORK_AND_EXACT_DOM"
    )
    encoded_user = result["terminal_evidence"]["serialized_user"]
    assert encoded_user["raw_sha256"] == digest(raw)
    assert encoded_user["logical_sha256"] == digest(prompt)
    assert encoded_user["round_trip"]
    assert store.one("SELECT * FROM turns WHERE id=?", (turn_id,)) == original
    assert (
        store.one("SELECT stage FROM rounds WHERE id=?", (row["id"],))["stage"]
        == "AWAITING_PARENT_RESPONSE"
    )
    assert len(store.query("SELECT * FROM parent_responses")) == 2
    assert len(store.query("SELECT * FROM rounds")) == 3
    assert commit_leaf_recovery(scheduler, turn_id, proof)["idempotent"]
    await scheduler.aclose()
