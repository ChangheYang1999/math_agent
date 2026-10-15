#!/usr/bin/env python3
"""Explicit one-off recovery of historical e3 in this disposable project only.

Default: fetch and verify evidence, write a new immutable audit, change no DB rows.
--apply: close only historical e3 as FAILED_NOT_SENT, advance epoch 3 -> 4,
then call standard Scheduler.recover() with a transport that cannot dispatch.
This is not a generic acknowledgement for interrupted or uncertain submissions.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[1]
PROJECT = BASE / "runs/20261014-live-r2/projects/tree"
OPERATION = "parent:n-e615a92f81c6-r000002"
RETRY_KEY = "retry:" + OPERATION
CONVERSATION = "6acf41ec-72f8-83ea-a670-bfd46819ef79"
OLD_CLIENT = "extension:tab:1707788673"
PIN = "0ffdae90239988f253058c05253226152acd55d2"
REQUESTS = [
    "mathagent_87686d9cb28355e7a2dc631bfdd0e020",
    "mathagent_c3b62eaee6945f11a6b807f2b92521ba",
    "mathagent_bd996b71a2295575853a8d3dd1e1896d",
    "mathagent_f5277c2710ed570d9b3e238a14ef7255",
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(value):
    if not isinstance(value, bytes):
        value = value.encode() if isinstance(value, str) else json.dumps(value, sort_keys=True).encode()
    return hashlib.sha256(value).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def local_snapshot():
    with sqlite3.connect((PROJECT / "tree.db").as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(row) for row in db.execute(
            "SELECT * FROM turns WHERE id IN (?,?,?,?) ORDER BY id",
            tuple(f"{OPERATION}:e{i}:a0" for i in range(4)),
        )]
        require(len(rows) == 4, "All four exact historical local attempts must exist")
        for epoch, row in enumerate(rows):
            require(row["bridge_request_id"] == REQUESTS[epoch], "Historical request identity changed")
            require(row["raw_response"] is None, "A historical turn already has a response")
            require(row["status"] == ("ERROR" if epoch == 3 else "FAILED_NOT_SENT"), "Unexpected historical status")
        require(all(len(row["prompt"]) == 13065 for row in rows),
                "The four original long inputs must remain complete")
        saved = sqlite3.connect((BASE / "runs/20261015-long-prompt/snapshots/tree_before.db").as_uri() + "?mode=ro", uri=True)
        try:
            for row in rows:
                original = saved.execute("SELECT prompt,bridge_request_id FROM turns WHERE id=?", (row["id"],)).fetchone()
                require(original == (row["prompt"], row["bridge_request_id"]),
                        "Historical payload differs from the immutable pre-work snapshot")
        finally:
            saved.close()
        retry = db.execute("SELECT value FROM settings WHERE key=?", (RETRY_KEY,)).fetchone()
        require(retry and json.loads(retry[0]) == 3, "Only exact retry epoch 3 may advance")
        require(not db.execute("SELECT 1 FROM turns WHERE id LIKE ?", (OPERATION + ":e4:%",)).fetchone(),
                "A fourth retry epoch already exists; do not create or repeat it")
        unresolved = [dict(row) for row in db.execute("SELECT * FROM errors WHERE resolved=0")]
        require(len(unresolved) == 1 and unresolved[0]["operation"] == OPERATION and unresolved[0]["node_id"] == "n-e615a92f81c6",
                "Standard recovery must release only this one historical error")
        completed = [dict(row) for row in db.execute(
            "SELECT t.prompt FROM turns t JOIN sessions s ON s.id=t.session_id "
            "WHERE s.node_id='root' AND t.status='COMPLETED' AND t.id LIKE 'parent:%' ORDER BY t.created_at,t.id"
        )]
        require(len(completed) == 2, "The fixed Parent must still have exactly two completed inputs")
        counts = dict(db.execute(
            "SELECT 'leaf_reports',count(*) FROM rounds WHERE report IS NOT NULL UNION ALL "
            "SELECT 'parent_responses',count(*) FROM parent_responses UNION ALL "
            "SELECT 'pending_approvals',count(*) FROM approvals WHERE status='PENDING'"
        ).fetchall())
        require(counts == {"leaf_reports": 4, "parent_responses": 2, "pending_approvals": 0},
                "Disposable P0 checkpoint counts changed; inspect before recovery")
        require(not db.execute("SELECT 1 FROM rounds WHERE stage IN ('PROMPT_APPROVAL','REPORT_APPROVAL')").fetchone(),
                "Unresolved gate transitions require separate review before standard recovery")
        binding = dict(db.execute("SELECT * FROM sessions WHERE node_id='root' AND active=1").fetchone())
        require(binding["bridge_session_id"] == CONVERSATION, "Parent conversation changed")
        return {"turns": rows, "completed_parent_inputs": completed, "counts": counts, "binding": binding}


def check_e0_source_and_snapshot(upstream):
    require(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=upstream, text=True).strip() == PIN,
            "Historical source proof requires the exact pinned upstream revision")
    source = subprocess.check_output(["git", "show", "HEAD:tools/chrome-bridge-extension/content/composerCommands.js"], cwd=upstream)
    status = read_json(BASE / "composer_fix_status.json")
    require(sha(source) == status["restored_HEAD_source_sha256"], "Original source hash mismatch")
    text = source.decode()
    enter = text.split("async function enterPrompt(", 1)[1].split("function submitComposer(", 1)[0]
    prepare = text.split("async function focusAndSetComposerText(", 1)[1].split("function setComposerTextByPaste(", 1)[0]
    require(enter.index("await focusAndSetComposerText") < enter.index("method = submitComposer"),
            "Original preparation was not demonstrably before the submission call")
    require("throw new Error('COMPOSER_TEXT_VERIFY_FAILED:" in prepare, "Original throw site changed")
    stall = read_json(BASE / "tree_parent_stall_state.json")
    require(stall["state"]["requestId"] == REQUESTS[0] and stall["state"]["submission"] == "accepted"
            and stall["state"]["output"] == "none" and stall["response_anchor"]["userTurnKey"] == "",
            "Original pre-interruption snapshot is not a matching unsubmitted boundary")
    audit = read_json(BASE / "tree_interruption_audit.json")["pre_submission_evidence"]
    require(not audit["response_user_turn_key"] and not audit["submitted_user_turn_key"]
            and not audit["assistant_turn_key"] and not audit["response_boundary_established"],
            "Original historical snapshot contains a submitted/assistant anchor")
    return {"pinned_revision": PIN, "source_sha256": sha(source),
            "stall_snapshot_sha256": sha((BASE / "tree_parent_stall_state.json").read_bytes()),
            "interruption_audit_sha256": sha((BASE / "tree_interruption_audit.json").read_bytes())}


def check_remote(epoch, local, remote, events):
    request_id = REQUESTS[epoch]
    require(remote["id"] == request_id and remote["status"] in {"interrupted", "cancelled"}
            and remote.get("output") is None, "Historical remote attempt is not authoritatively interrupted without output")
    require(remote["input"]["message"] == local["prompt"]
            and remote["input"]["sourceClientId"] == OLD_CLIENT
            and remote["input"]["sessionId"] == CONVERSATION, "Remote exact input/source/conversation mismatch")
    require(events and len(events) < 5000 and events[0]["type"] == "turn/queued", "Incomplete own event history")
    require(any(event["type"] in {"turn/interrupted", "turn/cancelled"} for event in events), "No authoritative terminal event")
    forbidden = {"prompt.sent", "prompt.submitted", "request.done", "turn/completed", "turn/completed_without_artifact",
                 "diagnostic.prompt.submit.attempt", "diagnostic.chat.prompt.submit.confirmed", "diagnostic.prompt.submit.already_confirmed",
                 "diagnostic.send_button.found", "diagnostic.send_button.not_found_form_submit_fallback",
                 "diagnostic.send_button.not_found_keyboard_fallback"}
    payloads = []
    for event in events:
        require(event["type"] not in forbidden, "Historical evidence crosses a Send/confirmation/completion boundary")
        data = event.get("data") or {}
        require(not data.get("requestId") or data["requestId"] == request_id, "Foreign request event")
        require(not (event["type"] == "request.effect.succeeded" and data.get("effectType") == "prompt.submit"),
                "A historical submit effect succeeded")
        payload = data.get("payload") or {}
        if payload:
            require(payload.get("requestId") == request_id, "Foreign diagnostic request")
            payloads.append(payload)
    if epoch:
        proof = [p for p in payloads if p.get("name") == "request.effect.cancelled"
                 and p.get("effectId") == request_id + ":prompt.submit:attempt:1"
                 and p.get("effectType") == "prompt.submit" and p.get("code") == "COMPOSER_TEXT_VERIFY_FAILED"
                 and p.get("provenNotExecuted") is True
                 and p.get("cancellationEvidence") == {"source": "composer_preparation", "reason": "submission_boundary_not_entered"}
                 and p.get("preconditions", {}).get("promptHash") == sha(local["prompt"])]
        require(len(proof) == 1, "Missing unique positive source cancellation proof before Send")
    else:
        require(any(p.get("name") == "composer.text_verify_failed" and p.get("expectedLength") == 13065
                    and p.get("actualLength") == 0 for p in payloads), "Original preparation-failure diagnostic missing")
    return {"request_id": request_id, "terminal_status": remote["status"], "prompt_sha256": sha(local["prompt"]),
            "turn_sha256": sha(remote), "events_sha256": sha(events), "event_count": len(events)}


async def main(args):
    snapshot = local_snapshot()
    ui = read_json(args.parent_ui)
    expected = snapshot["completed_parent_inputs"]
    require(ui["conversation_id"] == CONVERSATION and ui["trimmed_draft_characters"] == 0
            and ui["pasted_text_attachment_count"] == 0, "Parent UI is not the exact clear fixed conversation")
    require(ui["visible_user_message_text_lengths"] == [len(row["prompt"]) for row in expected]
            and ui.get("visible_user_message_sha256") == [sha(row["prompt"]) for row in expected],
            "The two complete observed Parent messages do not match local completed inputs")
    require(snapshot["binding"]["bridge_client_id"] == OLD_CLIENT,
            "The known historical database binding must remain unchanged until acknowledgement")
    observed_client_id = f"extension:tab:{ui['parent_tab']}"
    source = check_e0_source_and_snapshot(args.upstream)
    base_url = os.getenv("MATHAGENT_BRIDGE_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
    require(urlparse(base_url).hostname in {"127.0.0.1", "localhost", "::1"}, "Loopback bridge only")
    token = os.environ.get("MATHAGENT_BRIDGE_API_TOKEN", "")
    require(token, "Set MATHAGENT_BRIDGE_API_TOKEN in the environment; tokens are never persisted")
    full = []
    async with httpx.AsyncClient(base_url=base_url, headers={"Authorization": "Bearer " + token}, timeout=30) as client:
        for epoch, local in enumerate(snapshot["turns"]):
            request_id = REQUESTS[epoch]
            response, history = await asyncio.gather(client.get("/turns/" + request_id),
                client.get("/turns/" + request_id + "/events", params={"limit": 5000}))
            response.raise_for_status(); history.raise_for_status()
            remote, events = response.json()["turn"], history.json()["events"]
            full.append({"proof": check_remote(epoch, local, remote, events), "turn": remote, "events": events})
        clients = (await client.get("/browser/clients")).json()["clients"]
        def matches_conversation(candidate):
            url = urlparse(candidate.get("url") or (candidate.get("session") or {}).get("url") or "")
            return url.scheme == "https" and url.hostname == "chatgpt.com" and url.path.rstrip("/") == "/c/" + CONVERSATION
        connected_matches = [c for c in clients if c.get("ready") is True
                             and c.get("compatible") is not False and matches_conversation(c)]
        require(len(connected_matches) == 1 and connected_matches[0]["id"] == observed_client_id,
                "UI evidence must identify the unique connected client of the exact Parent conversation URL")
        current = connected_matches[0]
        require(not current.get("activeRequest") and not current.get("releasePending")
                and not current.get("quarantined"), "Parent client must be connected and idle before recovery")
    audit = {"at": datetime.now(UTC).isoformat(), "scope": "disposable historical e3 only; no Send",
             "local_turn_id": OPERATION + ":e3:a0", "request_id": REQUESTS[3],
             "previous_status": "ERROR", "new_status": "FAILED_NOT_SENT", "retry_key": RETRY_KEY,
             "previous_epoch": 3, "next_epoch": 4, "old_error": snapshot["turns"][3]["error"],
             "ui_evidence_sha256": sha(Path(args.parent_ui).read_bytes()), "source_proof": source,
             "binding_verification": {"stored_historical_client": OLD_CLIENT, "observed_client": observed_client_id,
                                      "conversation_id": CONVERSATION, "unique_connected_url_match": True,
                                      "rebind_performed": False},
             "remote": full, "planned_next_id_only_not_dispatched": OPERATION + ":e4:a0"}
    output = Path(args.output) if args.output else Path(args.parent_ui).parent / ("historical_e3_verified_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    with output.open("x") as file:
        json.dump(audit, file, indent=2); file.write("\n")
    if not args.apply:
        print(json.dumps({"status": "VERIFIED_READ_ONLY", "audit": str(output), "database_changed": False}))
        return
    sys.path.insert(0, str(REPO / "src"))
    from math_research_agent.store import Store
    from math_research_agent.scheduler import Scheduler

    class NoDispatch:
        def __getattr__(self, name):
            raise RuntimeError("No model dispatch is permitted by this recovery script: " + name)

    store = Store(PROJECT)
    scheduler = Scheduler(store, transport=NoDispatch())
    scheduler._acquire()
    try:
        require(local_snapshot() == snapshot, "Disposable state changed during verification")
        backup = output.with_suffix(".before.db")
        require(not backup.exists(), "Refusing to overwrite a prior backup")
        with sqlite3.connect((PROJECT / "tree.db").as_uri() + "?mode=ro", uri=True) as source_db, sqlite3.connect(backup) as destination:
            source_db.backup(destination)
        with store.transaction() as db:
            changed = db.execute("UPDATE turns SET status='FAILED_NOT_SENT' WHERE id=? AND status='ERROR' AND raw_response IS NULL AND bridge_request_id=?",
                (OPERATION + ":e3:a0", REQUESTS[3])).rowcount
            epoch_changed = db.execute("UPDATE settings SET value='4' WHERE key=? AND value='3'", (RETRY_KEY,)).rowcount
            require(changed == epoch_changed == 1, "Exact historical status/epoch compare-and-swap failed")
            store.event("experiment_historical_not_sent_acknowledged", {
                **{key: audit[key] for key in ["scope", "local_turn_id", "request_id", "previous_status", "new_status", "retry_key", "previous_epoch", "next_epoch"]},
                "immutable_audit": str(output), "immutable_audit_sha256": sha(output.read_bytes()),
                "raw_response_preserved_null": True, "error_preserved": True,
            }, db)
        recovery = scheduler.recover()
        for original in snapshot["turns"]:
            after = store.one("SELECT * FROM turns WHERE id=?", (original["id"],))
            expected_row = {**original, "status": "FAILED_NOT_SENT"}
            require(after == expected_row, "Recovery changed a historical prompt/error/response/identity")
        require(store.setting(RETRY_KEY) == 4 and not store.one("SELECT id FROM turns WHERE id LIKE ?", (OPERATION + ":e4:%",)),
                "Recovery unexpectedly dispatched or changed the explicit retry epoch")
        result = {"status": "APPLIED_NO_DISPATCH", "audit": str(output), "backup": str(backup), "recovery": recovery,
                  "changed_historical_turns": [OPERATION + ":e3:a0"], "retry_epoch": store.setting(RETRY_KEY), "prompts_sent": 0}
        with output.with_suffix(".result.json").open("x") as file:
            json.dump(result, file, indent=2); file.write("\n")
        print(json.dumps(result))
    finally:
        # Release only the local scheduler lock; never invoke transport methods.
        import fcntl
        fcntl.flock(scheduler._lockfile, fcntl.LOCK_UN)
        scheduler._lockfile.close()
        scheduler._lockfile = None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-ui", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, default=Path("/private/tmp/mathagent-upstream-bridge"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args()))
