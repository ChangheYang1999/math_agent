"""Explicit, source-bound Parent recovery without rewriting a failed browser turn."""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from .schemas import PARENT_MODEL, ParentRoundResponse
from .store import digest, encode

RECEIPT = "parent_recovery_committed"


def _json_text(text):
    if text.startswith("```json\n") and text.endswith("\n```"):
        return text[len("```json\n") : -len("\n```")]
    return text


def _unconfirmed_submission(proof, turn, session, *, baseline):
    """Only recorded source diagnostics; backend text must independently prove Send."""
    request_id, client = turn["bridge_request_id"], session["bridge_client_id"]

    def require(condition, message):
        if not condition:
            raise ValueError("Source recovery refused: " + message)

    def diagnostics(name):
        rows = [event for event in proof["events"] if event.get("type") == name]
        for event in rows:
            data = event.get("data") or {}
            require(
                data.get("requestId") == request_id and data.get("clientId") == client,
                "submission diagnostic source mismatch",
            )
        return [(event.get("data") or {}).get("payload") or {} for event in rows]

    effects = [
        event
        for event in proof["events"]
        if event.get("type") == "request.effect.started"
        and (event.get("data") or {}).get("effectType") == "prompt.submit"
    ]
    require(
        len(effects) == 1
        and effects[0]["data"].get("requestId") == request_id
        and effects[0]["data"].get("effectId") == request_id + ":prompt.submit:attempt:1",
        "one exact submission effect is required",
    )
    composer, button = (
        diagnostics("diagnostic.composer.text_verified"),
        diagnostics("diagnostic.send_button.found"),
    )
    armed, mismatch = (
        diagnostics("diagnostic.prompt.turn_boundary.armed"),
        diagnostics("diagnostic.prompt.user_turn_text_mismatch"),
    )
    require(
        len(composer) == len(button) == len(armed) == len(mismatch) == 1
        and composer[0].get("verification") == "full_text_equal"
        and composer[0].get("length") == len(turn["prompt"])
        and composer[0].get("sendReady") is True
        and button[0].get("attempt") == 1
        and button[0].get("kind") == "prompt"
        and armed[0].get("turnCount") == armed[0].get("baselineCount") == baseline,
        "exact composer/button/boundary proof is required",
    )
    candidates = mismatch[0].get("candidates") or []
    require(
        len(candidates) == 1
        and candidates[0].get("index") == baseline
        and 0 < candidates[0].get("textLength", 0) < len(turn["prompt"]),
        "one recorded rendering-mismatch candidate is required",
    )
    return candidates[0]


def _conversation(url):
    parsed = urlparse(url or "")
    if parsed.scheme != "https" or parsed.hostname not in {"chatgpt.com", "chat.openai.com"}:
        return None
    return parsed.path.split("/c/", 1)[1].strip("/") if "/c/" in parsed.path else None


def _turn_hash(turn):
    return digest(encode(turn))


def _committed_receipt(store, turn):
    for event in store.query(
        "SELECT payload FROM events WHERE type=? ORDER BY id DESC", (RECEIPT,)
    ):
        receipt = json.loads(event["payload"])
        if receipt.get("turn_id") != turn["id"]:
            continue
        response = store.one(
            "SELECT * FROM parent_responses WHERE round_id=?", (receipt["round_id"],)
        )
        round_ = store.one("SELECT * FROM rounds WHERE id=?", (receipt["round_id"],))
        node = store.node(round_["node_id"]) if round_ else None
        session = store.one("SELECT * FROM sessions WHERE id=?", (turn["session_id"],))
        if (
            receipt.get("original_turn_hash") == _turn_hash(turn)
            and receipt.get("request_id") == turn["bridge_request_id"]
            and receipt.get("session_id") == turn["session_id"]
            and re.fullmatch(
                r"parent:" + re.escape(receipt.get("round_id", "")) + r":e\d+:a\d+", turn["id"]
            )
            and session
            and session["node_id"] == receipt.get("parent_id")
            and session["bridge_session_id"] == receipt.get("conversation_id")
            and node
            and node["id"] == receipt.get("child_node_id")
            and node["parent_id"] == receipt.get("parent_id")
            and response
            and response["parent_id"] == receipt.get("parent_id")
            and response["next_round_id"] == receipt.get("next_round_id")
            and digest(response["payload"]) == receipt.get("parent_response_hash")
        ):
            return receipt
    return None


def unresolved_turns(store, session_id=None, excluding=None):
    """Only an exact committed recovery receipt releases an original failed turn."""
    rows = store.query(
        "SELECT * FROM turns WHERE raw_response IS NULL AND status!='FAILED_NOT_SENT' ORDER BY created_at,id"
    )
    return [
        row
        for row in rows
        if row["id"] != excluding
        and (session_id is None or row["session_id"] == session_id)
        and not (_committed_receipt(store, row) or _committed_leaf_receipt(store, row))
    ]


def _committed_leaf_receipt(store, turn):
    for event in store.query(
        "SELECT payload FROM events WHERE type='leaf_recovery_committed' ORDER BY id DESC"
    ):
        receipt = json.loads(event["payload"])
        if receipt.get("turn_id") != turn["id"]:
            continue
        round_ = store.one("SELECT * FROM rounds WHERE id=?", (receipt["round_id"],))
        session = store.one("SELECT * FROM sessions WHERE id=?", (turn["session_id"],))
        if (
            receipt.get("original_turn_hash") == _turn_hash(turn)
            and receipt.get("request_id") == turn["bridge_request_id"]
            and receipt.get("session_id") == turn["session_id"]
            and re.fullmatch(
                r"leaf:" + re.escape(receipt.get("round_id", "")) + r":e\d+:a\d+", turn["id"]
            )
            and (receipt.get("terminal_evidence") or {}).get("submission_authority")
            in {
                "AUTHENTICATED_NETWORK_USER_AND_FINAL_TEXT",
                "AUTHENTICATED_SERIALIZED_NETWORK_AND_EXACT_DOM",
            }
            and round_
            and round_["node_id"] == receipt.get("node_id")
            and digest(round_["report"] or "") == receipt.get("report_sha256")
            and store.node(round_["node_id"])["parent_id"] == receipt.get("parent_id")
            and session
            and session["node_id"] == receipt.get("node_id")
            and session["bridge_session_id"] == receipt.get("conversation_id")
        ):
            return receipt
    return None


def validate_history_capture(proof):
    """Check an actual owned-tab network record, without fabricating Bridge success."""

    def require(condition, message):
        if not condition:
            raise ValueError("Parent recovery refused: network history " + message)

    capture, observed = proof["authenticated_history"], proof["observation"]
    inp = proof["upstream"]["input"]
    conversation = inp["sessionId"]
    user_id = observed["userTurnKey"].removesuffix("::user")
    assistant_id = observed["assistantMessageId"]
    page = urlparse(observed["url"])
    require(
        page.scheme == "https"
        and page.hostname in {"chatgpt.com", "chat.openai.com"}
        and _conversation(observed["url"]) == conversation,
        "unsupported page origin",
    )
    expected_url = f"{page.scheme}://{page.netloc}/backend-api/conversation/{conversation}"
    require(
        capture.get("source") == "ACTUAL_OWN_TAB_NETWORK_RESPONSE"
        and str(capture.get("tabId")) == inp["sourceClientId"].removeprefix("extension:tab:")
        and capture.get("conversationUrl") == observed["url"]
        and capture.get("url") == expected_url
        and capture.get("status") == 200
        and capture.get("requestId"),
        "capture identity/status mismatch",
    )
    body = capture.get("body") or {}
    require(
        body.get("base64Encoded") is False and isinstance(body.get("body"), str),
        "unsupported body encoding",
    )
    record = json.loads(body["body"])
    mapping = record.get("mapping")
    require(
        record.get("conversation_id") == conversation and isinstance(mapping, dict),
        "conversation mismatch",
    )
    branch, seen, message_ids = [], set(), set()
    key = record.get("current_node")
    require(isinstance(key, str) and key, "current branch is missing")
    while key is not None:
        require(key not in seen and len(branch) < 10000, "invalid/cyclic branch")
        seen.add(key)
        node = mapping.get(key)
        require(
            isinstance(node, dict)
            and "parent" in node
            and (node["parent"] is None or isinstance(node["parent"], str)),
            "invalid ancestor",
        )
        message = node.get("message") or {}
        if message.get("id"):
            require(message["id"] not in message_ids, "duplicate message identity")
            message_ids.add(message["id"])
        branch.append(message)
        key = node["parent"]
    assistant = branch[0]
    user = next(
        (message for message in branch[1:] if (message.get("author") or {}).get("role") == "user"),
        {},
    )
    require(
        assistant.get("id") == assistant_id
        and (assistant.get("author") or {}).get("role") == "assistant"
        and user.get("id") == user_id,
        "exact assistant/user ancestor mismatch",
    )
    require(
        assistant.get("status") == "finished_successfully"
        and assistant.get("end_turn") is True
        and assistant.get("recipient") == "all"
        and assistant.get("channel") == "final",
        "assistant is not terminal final output",
    )

    def parts(message):
        content = message.get("content") or {}
        values = content.get("parts")
        require(
            content.get("content_type") == "text"
            and isinstance(values, list)
            and values
            and all(isinstance(part, str) for part in values),
            "unsupported message content",
        )
        return "".join(values)

    require(parts(user) == inp["message"], "submitted user text/hash mismatch")
    metadata = assistant.get("metadata") or {}
    require(
        metadata.get("resolved_model_slug") == metadata.get("model_slug") == "gpt-6-thinking"
        and metadata.get("thinking_effort") == "max"
        and metadata.get("is_complete") is True
        and (metadata.get("finish_details") or {}).get("type") == "stop",
        "Parent model/completion metadata mismatch",
    )
    require(
        metadata.get("request_id")
        and metadata["request_id"] == (user.get("metadata") or {}).get("request_id"),
        "native request identity mismatch",
    )
    raw = decoded = parts(assistant)
    if raw.startswith("<escape>"):
        constants = (metadata.get("model_dil_v2") or {}).get("constants") or {}
        require(
            set(constants) == {"0"}
            and isinstance(constants["0"], str)
            and raw == "<escape>" + constants["0"] + "</escape>",
            "rich-text round-trip mismatch",
        )
        decoded = constants["0"]  # Exact captured text; no unescaping or executable code.
    elif raw.startswith('<CodeBlock language="json" editable={false}>\n'):
        prefix, suffix = '<CodeBlock language="json" editable={false}>\n', "\n</CodeBlock>"
        require(raw.endswith(suffix), "literal JSON code-block wrapper mismatch")
        decoded = raw[len(prefix) : -len(suffix)]
        require(raw == prefix + decoded + suffix, "literal JSON code-block round-trip mismatch")
    require(
        encode(json.loads(decoded))
        == encode(json.loads(_json_text(observed["assistantCandidate"])))
        == encode(json.loads(_json_text(proof["recovered"]["answer"]))),
        "assistant JSON/string values mismatch",
    )
    return {
        "source": capture["source"],
        "capture_sha256": digest(encode(capture)),
        "network_request_id": capture["requestId"],
        "native_request_id": metadata["request_id"],
        "model_slug": metadata["resolved_model_slug"],
        "thinking_effort": metadata["thinking_effort"],
        "decoded_answer_sha256": digest(decoded),
        "user_sha256": digest(parts(user)),
    }


def validate_parent_recovery(store, turn_id, proof):
    """Validate GET evidence, a current DOM capture, and opt-in history reconciliation.

    proof keys: upstream (original failed turn), events (its complete event list),
    observation (requestId/url/userTurnKey/exactRenderedUserText/assistantMessageId/
    assistantCandidate), and recovered (the existing /browser/recover-latest result).
    This function does not contact the browser or mutate state.
    """

    def require(condition, message):
        if not condition:
            raise ValueError("Parent recovery refused: " + message)

    match = re.fullmatch(r"parent:(.+):e\d+:a\d+", turn_id)
    turn = store.one("SELECT * FROM turns WHERE id=?", (turn_id,))
    require(match and turn, "unknown exact Parent turn")
    round_ = store.one("SELECT * FROM rounds WHERE id=?", (match[1],))
    require(round_ and round_["report"] and round_["report_accepted"], "report is not accepted")
    require(
        round_["stage"] in {"AWAITING_PARENT_RESPONSE", "RESPONDED"}, "round is not recoverable"
    )
    child = store.node(round_["node_id"])
    session = store.one("SELECT * FROM sessions WHERE id=?", (turn["session_id"],))
    require(
        session and session["node_id"] == child["parent_id"] and session["model"] == PARENT_MODEL,
        "Parent session/role does not match the child",
    )
    upstream, events, observation, recovered = (
        proof[key] for key in ("upstream", "events", "observation", "recovered")
    )
    terminal_code = (upstream.get("error") or {}).get("code")
    unconfirmed = terminal_code == "CANONICAL_DEADLINE_EXCEEDED"
    require(
        turn["status"] == "ERROR"
        and turn["raw_response"] is None
        and terminal_code in {"CANONICAL_RECOVERY_UNCERTAIN", "CANONICAL_DEADLINE_EXCEEDED"}
        and terminal_code in (turn["error"] or ""),
        "original error must remain intact",
    )
    request_id, conversation = turn["bridge_request_id"], session["bridge_session_id"]
    require(
        upstream.get("id") == request_id
        and upstream.get("status") == "failed"
        and upstream.get("output") is None,
        "the exact failed upstream terminal is required",
    )
    inp = upstream.get("input") or {}
    require(
        inp.get("message") == turn["prompt"]
        and inp.get("sessionId") == conversation
        and inp.get("sourceClientId") == session["bridge_client_id"],
        "upstream input/binding mismatch",
    )
    metadata = inp.get("metadata") or {}
    require(
        metadata.get("researchNodeId") == child["parent_id"]
        and metadata.get("requiredModel") == session["bridge_model"]
        and session["bridge_model"] in {"model-gpt-6", "GPT-6", "GPT-6 Thinking"}
        and metadata.get("requiredEffort") == session["bridge_effort"] == "xhigh",
        "original required Parent model/effort mismatch",
    )
    confirmations = [
        event for event in events if event.get("type") == "diagnostic.chat.prompt.submit.confirmed"
    ]
    prompt_hash = digest(turn["prompt"])
    if unconfirmed:
        require(
            not confirmations
            and proof.get("authenticated_history")
            and upstream.get("completedAt")
            and round_["number"] == 1,
            "exact naturally failed first Parent assessment requires network authority",
        )
        user_key = _unconfirmed_submission(proof, turn, session, baseline=2).get("key") or ""
    else:
        require(len(confirmations) == 1, "exactly one confirmed Send is required")
        data = confirmations[0].get("data") or {}
        sent = data.get("payload") or {}
        require(
            data.get("requestId") == request_id
            and data.get("clientId") == session["bridge_client_id"]
            and sent.get("requestId") == request_id
            and sent.get("fullPromptTextMatch") is True
            and sent.get("expectedSha256") == sent.get("observedSha256") == prompt_hash
            and sent.get("expectedCharacters")
            == sent.get("observedCharacters")
            == len(turn["prompt"])
            and _conversation(sent.get("url")) == conversation,
            "full original Send proof mismatch",
        )
        user_key = sent.get("turnKey") or ""
    require(
        user_key.endswith("::user")
        and observation.get("userTurnKey", "").removesuffix("::user")
        == user_key.removesuffix("::user")
        and observation.get("requestId") == request_id
        and _conversation(observation.get("url")) == conversation
        and (unconfirmed or observation.get("exactRenderedUserText") == turn["prompt"]),
        "current exact user turn mismatch",
    )
    assistant_id = observation.get("assistantMessageId")
    require(
        assistant_id
        and encode(json.loads(_json_text(recovered.get("answer", ""))))
        == encode(json.loads(_json_text(observation.get("assistantCandidate", ""))))
        and recovered.get("sourceClientId") == session["bridge_client_id"]
        and (recovered.get("session") or {}).get("id") == conversation
        and _conversation(recovered.get("url")) == conversation,
        "recovered assistant source mismatch",
    )
    reconciliation = recovered.get("reconciliation") or {}
    terminal_proof = validate_history_capture(proof) if proof.get("authenticated_history") else None
    if unconfirmed:
        require(
            any(
                f'data-chatgpt-search-message-ids="{assistant_id} {assistant_id}"'
                in node.get("html", "")
                and f'data-chatgpt-selection-conversation-id="{conversation}"'
                in node.get("html", "")
                for node in observation.get("dom", [])
            ),
            "exact completed DOM assistant/conversation identity mismatch",
        )
        terminal_proof["submission_authority"] = "AUTHENTICATED_NETWORK_USER_AND_FINAL_TEXT"
        terminal_proof["confirmed_send_diagnostic"] = False
    require(
        terminal_proof
        or (
            reconciliation.get("source") == "conversation-record"
            and reconciliation.get("version") == 1
            and reconciliation.get("status") == "matched_complete"
            and reconciliation.get("reason") == "exact_branch_boundary"
            and reconciliation.get("conversationId") == conversation
            and reconciliation.get("userMessageId") == user_key.removesuffix("::user")
            and reconciliation.get("assistantMessageId") == assistant_id
            and reconciliation.get("backendStatus") == "finished_successfully"
            and reconciliation.get("endTurn") is True
            and reconciliation.get("textMatches") is True
        ),
        "exact branch/assistant identity/terminal completion proof is missing",
    )
    out = ParentRoundResponse.model_validate_json(_json_text(recovered["answer"]))
    require(
        out.child_node_id == child["id"] and out.responding_to_round_id == round_["id"],
        "structured Parent IDs do not match",
    )
    receipt = {
        "turn_id": turn_id,
        "request_id": request_id,
        "session_id": session["id"],
        "parent_id": child["parent_id"],
        "child_node_id": child["id"],
        "round_id": round_["id"],
        "conversation_id": conversation,
        "user_turn_key": user_key,
        "assistant_message_id": assistant_id,
        "original_turn_hash": _turn_hash(turn),
        "prompt_sha256": prompt_hash,
        "answer_sha256": digest(recovered["answer"]),
        "parent_response_hash": digest(encode(out)),
        "proof_sha256": digest(encode(proof)),
        "terminal_evidence": terminal_proof
        or {"source": "conversation-record", "reconciliation": reconciliation},
    }
    return out, receipt


def commit_parent_recovery(scheduler, turn_id, proof):
    """Explicitly commit a proven response/next prompt; never dispatch or alter the old turn.

    Caller must first back up the isolated project. The scheduler lock is retained
    until caller closes its scheduler. Original upstream and local failures stay intact.
    """
    if scheduler._tasks:
        raise ValueError("Stop the scheduler before explicit Parent reconciliation")
    scheduler._acquire()
    store = scheduler.store
    out, receipt = validate_parent_recovery(store, turn_id, proof)
    original = store.one("SELECT * FROM turns WHERE id=?", (turn_id,))
    previous = _committed_receipt(store, original)
    if previous:
        if previous["parent_response_hash"] != receipt["parent_response_hash"]:
            raise ValueError("A recovery receipt cannot be replaced by another response")
        return {**previous, "idempotent": True}
    existing = store.one("SELECT * FROM parent_responses WHERE round_id=?", (receipt["round_id"],))
    if existing and digest(existing["payload"]) != receipt["parent_response_hash"]:
        raise ValueError("The round already has a different Parent response")
    store.event("parent_recovery_validated", {**receipt, "proof": proof})
    # Existing P0 transaction persists the exact response and next prompt before
    # optional jobs. A crash before the receipt remains blocked and can reconcile.
    next_id = scheduler._commit_parent(receipt["round_id"], receipt["parent_id"], out)
    receipt["next_round_id"] = next_id
    with store.transaction() as connection:
        if (
            dict(connection.execute("SELECT * FROM turns WHERE id=?", (turn_id,)).fetchone())
            != original
        ):
            raise ValueError("The original failed turn changed during recovery")
        store.event(RECEIPT, receipt, connection)
    return {**receipt, "idempotent": False}
