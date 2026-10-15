"""Explicit recovery of a misparsed Pro final, preserving its original terminal."""

from __future__ import annotations

import json
import re
import string
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

from .recovery import _conversation, _turn_hash, _unconfirmed_submission
from .schemas import PRO_MODEL, LeafRoundReport
from .store import digest, encode

RECEIPT = "leaf_recovery_committed"


def _require(condition, message):
    if not condition:
        raise ValueError("Leaf recovery refused: " + message)


def _text(message):
    content = message.get("content") or {}
    parts = content.get("parts")
    _require(
        content.get("content_type") == "text"
        and isinstance(parts, list)
        and parts
        and all(isinstance(part, str) for part in parts),
        "unsupported authoritative text",
    )
    return "".join(parts)


def _failed_first_submission(proof, turn, session):
    candidate = _unconfirmed_submission(proof, turn, session, baseline=0)
    _require(
        candidate["textLength"] == len(turn["prompt"]) - 2,
        "unexpected first-turn rendering mismatch",
    )
    return candidate.get("key") or ""


def _later_submission(proof, turn, session):
    mismatches = [
        e for e in proof["events"] if e.get("type") == "diagnostic.prompt.user_turn_text_mismatch"
    ]
    _require(mismatches, "missing later-round user identity diagnostics")
    keys = set()
    for event in mismatches:
        data = event.get("data") or {}
        candidates = (data.get("payload") or {}).get("candidates") or []
        _require(
            data.get("requestId") == turn["bridge_request_id"]
            and data.get("clientId") == session["bridge_client_id"]
            and len(candidates) == 1
            and candidates[0].get("index") == 4,
            "later-round mismatch source/candidate is ambiguous",
        )
        keys.add(candidates[0].get("key"))
    _require(len(keys) == 1, "later-round mismatch user identity changed")
    # Check the one-attempt/composer/baseline guards using the first actual
    # diagnostic; every repeated diagnostic above remains in the saved proof.
    selected = {
        **proof,
        "events": [
            e
            for e in proof["events"]
            if e.get("type") != "diagnostic.prompt.user_turn_text_mismatch" or e is mismatches[0]
        ],
    }
    return _unconfirmed_submission(selected, turn, session, baseline=4).get("key") or ""


def _serialized_user(user, proof, prompt, conversation):
    """Reversible CommonMark escape trace, only in an observed plain rich context."""
    _require(
        (user.get("metadata") or {}).get("serialization_metadata") == {"render_format": "markdown"},
        "unsupported later-round user serialization",
    )
    raw, text, trace, index = _text(user), [], [], 0
    while index < len(raw):
        if (
            raw[index] == "\\"
            and index + 1 < len(raw)
            and raw[index + 1] in string.punctuation + "\n"
        ):
            trace.append({"logical_offset": len(text), "character": raw[index + 1]})
            text.append(raw[index + 1])
            index += 2
        else:
            text.append(raw[index])
            index += 1
    logical = "".join(text)
    offsets = {entry["logical_offset"] for entry in trace}
    encoded = "".join(("\\" if i in offsets else "") + ch for i, ch in enumerate(logical))
    _require(
        logical == prompt and encoded == raw,
        "serialized user logical text/trace round-trip mismatch",
    )
    rich, identity = proof.get("rich_user") or {}, proof.get("user_identity") or {}

    class PlainRich(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tags, self.parts, self.root = [], [], False

        def handle_starttag(self, tag, attrs):
            _require(
                tag in {"div", "p", "span", "br"}, "rich user is not a plain text/break context"
            )
            if not self.tags:
                self.root = (
                    tag == "div" and dict(attrs).get("data-markdown-text-tone") == "user-message"
                )
            self.tags.append(tag)
            if tag == "br":
                self.parts.append("\n")

        def handle_data(self, data):
            self.parts.append(data)

        def handle_comment(self, data):
            _require(False, "rich user has an unsupported comment")

    parser = PlainRich()
    parser.feed(rich.get("html", ""))
    _require(
        parser.root
        and parser.tags.count("div") == parser.tags.count("p") == 1
        and "".join(parser.parts) == rich.get("text") == prompt
        and _conversation(rich.get("url")) == _conversation(identity.get("url")) == conversation,
        "exact plain rich user literal does not match the original input",
    )
    ancestors = [
        a
        for a in identity.get("ancestors", [])
        if dict(a.get("attributes", [])).get("data-chatgpt-search-message-ids") == user["id"]
        and dict(a.get("attributes", [])).get("data-chatgpt-search-unit-key") == rich.get("key")
        and rich["html"] in a.get("html", "")
    ]
    _require(
        len(ancestors) == 1
        and any(
            n.get("key") == rich.get("key") and rich["html"] in n.get("html", "")
            for n in proof["observation"].get("dom", [])
        ),
        "native user ancestor/rich DOM identity mismatch",
    )
    return {
        "format": "markdown",
        "raw_characters": len(raw),
        "raw_sha256": digest(raw),
        "logical_characters": len(logical),
        "logical_sha256": digest(logical),
        "escape_trace": trace,
        "escape_trace_sha256": digest(encode(trace)),
        "round_trip": True,
        "encoder_limit": "Logical text plus preserved fixed-grammar escape trace; no claim to know the server's minimal encoder.",
    }


def validate_leaf_recovery(store, turn_id, proof):
    """Pure validation of the observed paged Pro history, exact Send, and DOM identity.

    The network final is the content authority. Rendered Markdown can lose math
    delimiters, so neither a reasoning recap nor reconstructed DOM text replaces it.
    proof contains upstream, events, authenticated_history (original capture), and
    observation(requestId/tabId/url/dom), with dom the original captured node list.
    """
    match = re.fullmatch(r"leaf:(.+):e\d+:a\d+", turn_id)
    turn = store.one("SELECT * FROM turns WHERE id=?", (turn_id,))
    _require(match and turn, "unknown exact Leaf turn")
    round_ = store.one("SELECT * FROM rounds WHERE id=?", (match[1],))
    _require(
        round_
        and round_["stage"]
        in {"SOLVING", "REPORT_APPROVAL", "AWAITING_PARENT_RESPONSE", "RESPONDED"},
        "round is not recoverable",
    )
    node = store.node(round_["node_id"])
    session = store.one("SELECT * FROM sessions WHERE id=?", (turn["session_id"],))
    _require(
        session
        and session["node_id"] == node["id"]
        and session["model"] == PRO_MODEL
        and session["bridge_model"] == "model-gpt-6"
        and session["bridge_effort"] == "effort-pro-pro"
        and not store.children(node["id"]),
        "exact genuine Pro Leaf binding is required",
    )
    failed_first = (
        turn["status"] == "ERROR"
        and turn["raw_response"] is None
        and "CANONICAL_CONVERSATION_CHANGED" in (turn["error"] or "")
    )
    later = (
        round_["number"] == 3
        and turn["status"] == "ERROR"
        and turn["raw_response"] is None
        and "CANONICAL_DEADLINE_EXCEEDED" in (turn["error"] or "")
    )
    _require(
        later
        or failed_first
        or (turn["status"] == "INVALID" and turn["raw_response"] and turn["error"]),
        "original parse/failure must remain intact",
    )
    _require(
        not store.query(
            "SELECT id FROM turns WHERE session_id=? AND id!=? AND created_at>=?",
            (session["id"], turn_id, turn["created_at"]),
        ),
        "later/ambiguous local session turn",
    )
    upstream, observed = proof["upstream"], proof["observation"]
    request_id = turn["bridge_request_id"]
    conversation = session["bridge_session_id"] or _conversation(observed.get("url"))
    _require(
        conversation and not conversation.startswith("local-chatgpt"),
        "persistent conversation proof is required",
    )
    response = (upstream.get("output") or {}).get("response") or {}
    inp = upstream.get("input") or {}
    client = session["bridge_client_id"]
    _require(
        upstream.get("id") == request_id and upstream.get("completedAt"),
        "original terminal identity is required",
    )
    if later:
        _require(
            upstream.get("status") == "failed"
            and upstream.get("output") is None
            and (upstream.get("error") or {}).get("code") == "CANONICAL_DEADLINE_EXCEEDED"
            and inp.get("sessionId") == conversation
            and session["bridge_session_id"] == conversation,
            "exact later-round natural terminal/binding is required",
        )
        prior = store.one(
            "SELECT r.report_accepted,p.next_round_id FROM rounds r JOIN parent_responses p ON p.round_id=r.id WHERE r.id=?",
            (round_["previous_round_id"],),
        )
        _require(
            prior and prior["report_accepted"] and prior["next_round_id"] == round_["id"],
            "later-round mandatory Parent link is missing",
        )
    elif failed_first:
        _require(
            upstream.get("status") == "failed"
            and upstream.get("output") is None
            and (upstream.get("error") or {}).get("code") == "CANONICAL_CONVERSATION_CHANGED"
            and inp.get("sessionId") == ""
            and round_["number"] == 1
            and session["bridge_session_id"] in {None, conversation}
            and session["url"] in {None, observed.get("url")},
            "exact failed first-turn/unbound source is required",
        )
    else:
        _require(
            upstream.get("status") == "completed"
            and upstream.get("error") is None
            and (upstream.get("output") or {}).get("answer") == turn["raw_response"]
            and response.get("answer") == turn["raw_response"]
            and response.get("requestId") == request_id
            and response.get("sourceClientId") == client
            and (response.get("session") or {}).get("id") == conversation
            and _conversation(response.get("url")) == _conversation(session["url"]) == conversation,
            "original completed terminal/binding mismatch",
        )
    metadata = inp.get("metadata") or {}
    _require(
        inp.get("message") == turn["prompt"]
        and inp.get("sourceClientId") == client
        and inp.get("sessionId") in {"", conversation}
        and metadata.get("researchNodeId") == node["id"]
        and metadata.get("requiredModel") == session["bridge_model"]
        and metadata.get("requiredEffort") == session["bridge_effort"],
        "original full input/role mismatch",
    )
    confirmations = [
        event
        for event in proof["events"]
        if event.get("type") == "diagnostic.chat.prompt.submit.confirmed"
    ]
    prompt_hash = digest(turn["prompt"])
    if later:
        _require(not confirmations, "later-round network authority cannot replace a confirmed Send")
        user_key = _later_submission(proof, turn, session)
    elif failed_first:
        _require(not confirmations, "failed first-turn path cannot replace a confirmed Send")
        user_key = _failed_first_submission(proof, turn, session)
    else:
        _require(len(confirmations) == 1, "exactly one confirmed Send is required")
        data = confirmations[0].get("data") or {}
        sent = data.get("payload") or {}
        sent_conversation = _conversation(sent.get("url"))
        _require(
            data.get("requestId") == sent.get("requestId") == request_id
            and data.get("clientId") == client
            and sent.get("confirmed") is True
            and sent.get("fullPromptTextMatch") is True
            and sent.get("expectedSha256") == sent.get("observedSha256") == prompt_hash
            and sent.get("expectedCharacters")
            == sent.get("observedCharacters")
            == len(turn["prompt"])
            and (
                sent_conversation == conversation
                or (
                    inp["sessionId"] == ""
                    and (sent_conversation or "").startswith("local-chatgpt%3A")
                )
            ),
            "full original Send proof mismatch",
        )
        user_key = sent.get("turnKey") or ""
    _require(user_key.endswith("::user"), "missing confirmed user identity")
    user_id = user_key.removesuffix("::user")
    _require(
        observed.get("requestId") == request_id
        and str(observed.get("tabId")) == client.removeprefix("extension:tab:")
        and _conversation(observed.get("url")) == conversation,
        "owned DOM observation binding mismatch",
    )
    capture = proof["authenticated_history"]
    route, body = capture.get("route") or {}, capture.get("response") or {}
    url = urlparse(route.get("url") or "")
    _require(
        str(capture.get("tabId")) == str(observed["tabId"])
        and route.get("status") == 200
        and route.get("requestId")
        and url.scheme == "https"
        and url.netloc == "chatgpt.com"
        and url.path == f"/backend-api/conversations/{conversation}"
        and parse_qs(url.query) == {"num_turns": ["10"], "include_has_versions": ["true"]}
        and body.get("base64Encoded") is False
        and isinstance(body.get("body"), str),
        "observed network identity/status/encoding mismatch",
    )
    history = json.loads(body["body"])
    messages, page = history.get("messages"), history.get("page_info") or {}
    _require(
        history.get("conversation_id") == conversation
        and history.get("default_model_slug") == "gpt-6-pro"
        and isinstance(messages, list)
        and len(messages) >= 2
        and page.get("has_previous_page") is False
        and page.get("has_next_page") is False,
        "complete genuine Pro conversation page is required",
    )
    ids = [message.get("id") for message in messages]
    _require(
        all(ids)
        and len(ids) == len(set(ids))
        and page.get("start_cursor") == ids[0]
        and page.get("end_cursor") == ids[-1],
        "inconsistent page/message identities",
    )
    selected_messages = messages
    if later:
        starts = [i for i, message in enumerate(messages) if message.get("id") == user_id]
        _require(len(starts) == 1, "exact later-round user is missing/duplicated")
        selected_messages = messages[starts[0] :]
    user, assistant = selected_messages[0], selected_messages[-1]
    serialized_user = _serialized_user(user, proof, turn["prompt"], conversation) if later else None
    assistant_id = assistant.get("id")
    _require(
        user.get("id") == user_id
        and (user.get("author") or {}).get("role") == "user"
        and (serialized_user or _text(user) == turn["prompt"])
        and history.get("current_node") == assistant_id
        and (assistant.get("author") or {}).get("role") == "assistant"
        and assistant.get("status") == "finished_successfully"
        and assistant.get("end_turn") is True
        and assistant.get("recipient") == "all"
        and assistant.get("channel") == "final"
        and not any(
            (message.get("author") or {}).get("role") == "user" or message.get("channel") == "final"
            for message in selected_messages[1:-1]
        ),
        "exact user/current terminal final mismatch or superseding turn",
    )
    exchange = (user.get("metadata") or {}).get("turn_exchange_id")
    _require(
        exchange
        and all(
            (message.get("metadata") or {}).get("turn_exchange_id")
            == (message.get("metadata") or {}).get("working_turn_id")
            == exchange
            for message in selected_messages
        ),
        "native exchange/working-turn identity mismatch",
    )
    metadata = assistant.get("metadata") or {}
    _require(
        all(
            metadata.get(key) == "gpt-6-pro"
            for key in ("model_slug", "resolved_model_slug", "default_model_slug")
        ),
        "actual final model is not genuine Pro",
    )
    native_request = (user.get("metadata") or {}).get("request_id")
    _require(
        native_request
        and metadata.get("request_id")
        and native_request in str(metadata.get("async_source") or ""),
        "async native request provenance mismatch",
    )
    dom = observed.get("dom") or []
    matching = [
        item
        for item in dom
        if f'data-chatgpt-search-message-ids="{assistant_id} {assistant_id}"'
        in item.get("html", "")
        and f'data-chatgpt-selection-conversation-id="{conversation}"' in item.get("html", "")
    ]
    _require(len(matching) == 1, "exact DOM assistant/conversation identity mismatch")
    answer = _text(assistant)
    json_answer = answer
    if answer.startswith("```json\n") and answer.endswith("\n```"):
        json_answer = answer[len("```json\n") : -len("\n```")]
    out = LeafRoundReport.model_validate_json(json_answer)
    _require(
        out.node_id == node["id"] and out.round_id == round_["id"], "structured Leaf IDs mismatch"
    )
    _require(
        encode(json.loads(json_answer)) == encode(out),
        "schema normalization would change source field values",
    )
    receipt = {
        "turn_id": turn_id,
        "request_id": request_id,
        "session_id": session["id"],
        "node_id": node["id"],
        "round_id": round_["id"],
        "parent_id": node["parent_id"],
        "conversation_id": conversation,
        "user_turn_key": user_key,
        "assistant_message_id": assistant_id,
        "original_turn_hash": _turn_hash(turn),
        "original_terminal_sha256": digest(encode(upstream)),
        "prompt_sha256": prompt_hash,
        "answer_sha256": digest(answer),
        "report_sha256": digest(encode(out)),
        "proof_sha256": digest(encode(proof)),
        "terminal_evidence": {
            "source": "ACTUAL_OWN_TAB_NETWORK_RESPONSE",
            "capture_sha256": digest(encode(capture)),
            "network_request_id": route["requestId"],
            "exchange_id": exchange,
            "native_user_request_id": native_request,
            "native_final_request_id": metadata["request_id"],
            "model_slug": metadata["resolved_model_slug"],
            "content_authority": "AUTHENTICATED_NETWORK_FINAL_TEXT",
            "dom_content_fidelity": "NOT_ASSUMED",
        },
    }
    if failed_first or later:
        receipt["terminal_evidence"]["submission_authority"] = (
            "AUTHENTICATED_NETWORK_USER_AND_FINAL_TEXT"
        )
        receipt["terminal_evidence"]["confirmed_send_diagnostic"] = False
    if later:
        receipt["terminal_evidence"]["submission_authority"] = (
            "AUTHENTICATED_SERIALIZED_NETWORK_AND_EXACT_DOM"
        )
        receipt["terminal_evidence"]["serialized_user"] = serialized_user
    return out, receipt


def commit_leaf_recovery(scheduler, turn_id, proof):
    """Explicit, idempotent local report/gate commit; no Send, Parent call, or retry."""
    _require(not scheduler._tasks, "stop the scheduler before reconciliation")
    scheduler._acquire()
    store = scheduler.store
    original = store.one("SELECT * FROM turns WHERE id=?", (turn_id,))
    previous = store.query("SELECT payload FROM events WHERE type=? ORDER BY id DESC", (RECEIPT,))
    for event in previous:
        saved = json.loads(event["payload"])
        if saved.get("turn_id") == turn_id:
            round_ = store.one("SELECT * FROM rounds WHERE id=?", (saved["round_id"],))
            session = store.one("SELECT * FROM sessions WHERE id=?", (saved["session_id"],))
            upstream = proof.get("upstream") or {}
            response = (upstream.get("output") or {}).get("response") or {}
            capture = proof.get("authenticated_history") or {}
            history = json.loads((capture.get("response") or {}).get("body", "{}"))
            encoded_user = saved.get("terminal_evidence", {}).get("serialized_user")
            selected_user = [
                m
                for m in history.get("messages", [])
                if m.get("id", "") + "::user" == saved["user_turn_key"]
            ]
            _require(
                original
                and saved["original_turn_hash"] == _turn_hash(original)
                and saved["prompt_sha256"] == digest(original["prompt"])
                and saved["proof_sha256"] == digest(encode(proof))
                and saved["original_terminal_sha256"] == digest(encode(upstream))
                and saved["request_id"] == original["bridge_request_id"] == upstream.get("id")
                and saved["session_id"] == original["session_id"]
                and re.fullmatch(r"leaf:" + re.escape(saved["round_id"]) + r":e\d+:a\d+", turn_id)
                and round_
                and round_["node_id"] == saved["node_id"]
                and store.node(saved["node_id"])["parent_id"] == saved["parent_id"]
                and digest(round_["report"] or "") == saved["report_sha256"]
                and session
                and session["node_id"] == saved["node_id"]
                and session["bridge_session_id"] == saved["conversation_id"]
                and (upstream.get("input") or {}).get("sourceClientId")
                == session["bridge_client_id"]
                and (
                    (
                        (upstream.get("error") or {}).get("code"),
                        saved["terminal_evidence"].get("submission_authority"),
                    )
                    in {
                        (
                            "CANONICAL_CONVERSATION_CHANGED",
                            "AUTHENTICATED_NETWORK_USER_AND_FINAL_TEXT",
                        ),
                        (
                            "CANONICAL_DEADLINE_EXCEEDED",
                            "AUTHENTICATED_SERIALIZED_NETWORK_AND_EXACT_DOM",
                        ),
                    }
                    or (
                        response.get("sourceClientId") == session["bridge_client_id"]
                        and (response.get("session") or {}).get("id") == saved["conversation_id"]
                    )
                )
                and history.get("conversation_id") == saved["conversation_id"]
                and history.get("current_node") == saved["assistant_message_id"]
                and (
                    (
                        encoded_user
                        and len(selected_user) == 1
                        and digest(_text(selected_user[0])) == encoded_user["raw_sha256"]
                        and digest(original["prompt"]) == encoded_user["logical_sha256"]
                    )
                    or (
                        not encoded_user
                        and history.get("messages", [{}])[0].get("id") + "::user"
                        == saved["user_turn_key"]
                    )
                ),
                "committed receipt/source/report changed",
            )
            return {**saved, "idempotent": True}
    out, receipt = validate_leaf_recovery(store, turn_id, proof)
    store.event("leaf_recovery_validated", {**receipt, "proof": proof})
    with store.transaction() as connection:
        session = dict(
            connection.execute(
                "SELECT * FROM sessions WHERE id=?", (receipt["session_id"],)
            ).fetchone()
        )
        _require(
            session["bridge_session_id"] in {None, receipt["conversation_id"]},
            "another conversation is already bound",
        )
        if session["bridge_session_id"] is None:
            connection.execute(
                "UPDATE sessions SET bridge_session_id=?,url=?,bridge_state='BOUND' WHERE id=?",
                (receipt["conversation_id"], proof["observation"]["url"], receipt["session_id"]),
            )
        scheduler._commit_leaf_report(receipt["round_id"], out, connection=connection)
        _require(
            dict(connection.execute("SELECT * FROM turns WHERE id=?", (turn_id,)).fetchone())
            == original,
            "original terminal changed during recovery",
        )
        store.event(RECEIPT, receipt, connection)
    return {**receipt, "idempotent": False}
