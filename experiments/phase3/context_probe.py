#!/usr/bin/env python3
"""Two capped, diagnostic-only recall turns after the six live research pairs."""

from __future__ import annotations

import asyncio
import fcntl
import json

from run_live import HERE, Phase3, digest, redact, stamp

from math_research_agent.schemas import LeafRoundReport

PROMPT = (
    "DIAGNOSTIC_CONTEXT_RECALL_ONLY. This is a read-only conversation-memory check, "
    "not another research round. Do not conduct mathematical research, propose tasks, "
    "change a research claim, or begin a LeafRoundReport. Look back at the FIRST "
    "assistant message in THIS conversation that returned a LeafRoundReport. "
    "Return exactly one JSON object with only the three string fields node_id, "
    "round_id, and summary. Copy those three values verbatim from that first "
    "assistant report, including its complete original summary, without paraphrasing. "
    "Do not use the most recent report. No expected values or research context are "
    "supplied here. If a value cannot be recalled, use an empty string rather than "
    "guessing. Return no Markdown fences or explanation. This diagnostic does not "
    "authorize any further research or require a Parent response."
)


def parse_json(raw):
    text = raw.strip()
    if text.startswith("```") and text.endswith("```"):
        text = "\n".join(text.splitlines()[1:-1])
    return json.loads(text)


async def require_idle(bridge):
    health = await bridge._json("GET", "/health")
    if any(health.get(key) for key in ("activeRequests", "pendingRequests", "pendingCommands")):
        raise ValueError("Bridge work remains active; no recall turn may be dispatched")
    if bridge.store.one(
        "SELECT id FROM turns WHERE raw_response IS NULL AND status!='FAILED_NOT_SENT'"
    ):
        raise ValueError("An unresolved durable turn remains; never submit another turn")


async def run(harness):
    bridge = harness.bridge()
    store = bridge.store
    result = {
        "started": stamp(),
        "kind": "DIAGNOSTIC_CONTEXT_RECALL_ONLY",
        "live_or_mock": "live",
        "flag": harness.data["flag"],
        "prompt": PROMPT,
        "attempts": [],
        "verdict": "NOT_RUN",
    }
    active_turn = None

    def save():
        harness.files.atomic_write(
            "context_probe.json", json.dumps(redact(result), indent=2) + "\n"
        )

    if (harness.root / "context_probe.json").exists():
        raise ValueError(
            "Recall evidence already exists; preserve it without repeating a submission"
        )
    try:
        if harness.data.get("halt"):
            raise ValueError("The research experiment is halted; no diagnostic inference permitted")
        if store.one("SELECT COUNT(*) AS n FROM parent_responses")["n"] != 6:
            raise ValueError("Exactly six completed research pairs are required first")
        children = store.children("root")
        if len(children) != 2 or any(node["status"] != "PAUSED" for node in children):
            raise ValueError("Exactly two paused experimental leaves are required")
        if any(store.is_internal(node["id"]) for node in children):
            raise ValueError("The original two-leaf topology must remain unchanged")
        if store.one("SELECT id FROM approvals WHERE status='PENDING'"):
            raise ValueError("A human approval remains pending; do not bypass it")
        await require_idle(bridge)
        ledger = json.loads((HERE / "request_ledger.json").read_text())
        if ledger.get("hard_cap") != 16 or len(ledger["requests"]) + 2 > 16:
            raise ValueError("Two diagnostic turns do not fit the global 16-request cap")
        plans = []
        for node in children:
            first = store.one("SELECT * FROM rounds WHERE node_id=? AND number=1", (node["id"],))
            turns = (
                store.query(
                    "SELECT * FROM turns WHERE id LIKE ? AND status='COMPLETED' AND raw_response IS NOT NULL",
                    ("leaf:" + first["id"] + ":%",),
                )
                if first
                else []
            )
            if len(turns) != 1 or not first["report_accepted"]:
                raise ValueError(
                    "The first report must have exactly one complete accepted source turn"
                )
            raw_report = parse_json(turns[0]["raw_response"])
            report = LeafRoundReport.model_validate(raw_report)
            if (report.node_id, report.round_id) != (node["id"], first["id"]):
                raise ValueError("First report source identity does not match its durable round")
            if report != LeafRoundReport.model_validate_json(first["report"]):
                raise ValueError("Stored report differs from its actual first assistant reply")
            expected = {key: raw_report[key] for key in ("node_id", "round_id", "summary")}
            if any(value in PROMPT for value in expected.values()):
                raise ValueError("Expected recall values must not appear in the diagnostic prompt")
            turn_id = "context-only:" + node["id"]
            if store.one("SELECT id FROM turns WHERE id=?", (turn_id,)):
                raise ValueError("Diagnostic turn identity already exists; never POST it again")
            session = store.one(
                "SELECT * FROM sessions WHERE node_id=? AND active=1", (node["id"],)
            )
            if not session or not session["bridge_session_id"]:
                raise ValueError("The leaf lacks its original persistent conversation binding")
            plans.append((turn_id, session["id"], expected))
        await harness.verify("tree")
        save()
        for turn_id, session_id, expected in plans:
            if harness.data.get("halt"):
                raise ValueError("Experiment halted; no further diagnostic inference permitted")
            await require_idle(bridge)
            active_turn = turn_id
            session = bridge.get_session(session_id)
            attempt = {
                "turn_id": turn_id,
                "started": stamp(),
                "expected": expected,
                "binding_before": harness.binding(bridge, session_id),
                "verdict": "PENDING",
            }
            result["attempts"].append(attempt)
            save()
            await bridge.send_message(session, PROMPT, turn_id)
            raw = await bridge.await_response(session, turn_id)
            evidence = await harness.own_evidence(bridge, turn_id)
            after = harness.binding(bridge, session_id)
            returned = parse_json(raw)
            prompt_hash = digest(PROMPT)
            full_send = any(
                event.get("type") == "diagnostic.chat.prompt.submit.confirmed"
                and (payload := event.get("data", {}).get("payload", {})).get("fullPromptTextMatch")
                is True
                and payload.get("expectedSha256") == payload.get("observedSha256") == prompt_hash
                and payload.get("observedCharacters") == len(PROMPT)
                for event in evidence.get("events", [])
            )
            remote = evidence.get("turn") or {}
            response = (remote.get("output") or {}).get("response") or {}
            attempt.update(
                {
                    "finished": stamp(),
                    "request_id": evidence.get("request_id"),
                    "raw_reply": raw,
                    "returned": returned,
                    "binding_after": after,
                    "same_binding": attempt["binding_before"] == after,
                    "full_submitted_text_verified": full_send,
                    "terminal_status": remote.get("status"),
                    "exact_recall": returned == expected,
                }
            )
            passed = (
                remote.get("status") == "completed"
                and response.get("answer") == raw
                and attempt["same_binding"]
                and full_send
                and returned == expected
                and not harness.data.get("halt")
            )
            attempt["verdict"] = "LIVE_PASS" if passed else "LIVE_FAIL"
            save()
            if not passed:
                raise ValueError(
                    "Diagnostic recall/binding/send proof failed; no second attempt permitted"
                )
        result["verdict"] = "LIVE_PASS"
        harness.data["phases"]["diagnostic_context_recall_pass"] = True
    except Exception as exc:
        result.update(
            {"verdict": "LIVE_FAIL_OR_UNCERTAIN" if active_turn else "BLOCKED", "error": str(exc)}
        )
        if active_turn:
            harness.halt("Diagnostic-only recall stopped: " + str(exc), active_turn)
        save()
        raise
    finally:
        result["finished"] = stamp()
        save()
        if active_turn:
            try:
                await harness.export()
            except Exception as exc:
                result["export_error"] = str(exc)
                save()
        harness.save()
        await bridge.aclose()
    return result


async def main():
    lock = (HERE / "runs/live/.command.lock").open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = await run(Phase3())
        print(json.dumps(redact(result), indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc), "evidence": "runs/live/context_probe.json"}, indent=2))
        return 1
    finally:
        lock.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
