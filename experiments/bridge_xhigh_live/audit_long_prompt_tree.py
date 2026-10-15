#!/usr/bin/env python3
"""Audit saved continuation evidence through SQLite read-only transactions only."""

import argparse
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from math_research_agent.config import Config
from math_research_agent.schemas import LeafRoundReport, ParentRoundResponse, PARENT_MODEL, PRO_MODEL

BASE = Path(__file__).resolve().parent


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def snapshot(path):
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        return {table: [dict(row) for row in connection.execute("SELECT * FROM " + table)]
                for table in ("settings", "nodes", "sessions", "turns", "rounds", "parent_responses", "artifacts", "approvals", "events")}


def audit(before, after):
    checks = {}
    old_rounds = {r["id"]: r for r in before["rounds"]}
    rounds = {r["id"]: r for r in after["rounds"]}
    old_pairs = {r["round_id"]: r for r in before["parent_responses"]}
    pairs = {r["round_id"]: r for r in after["parent_responses"]}
    sessions = {s["id"]: s for s in after["sessions"]}
    events = [{**e, "decoded": json.loads(e["payload"])} for e in after["events"]]

    def event_id(kind, round_id):
        return next((e["id"] for e in events if e["type"] == kind and e["decoded"].get("round_id") == round_id), None)

    report_rows = []
    for round_id, old in old_rounds.items():
        if not old["report"]:
            continue
        current = rounds[round_id]
        report = LeafRoundReport.model_validate_json(current["report"])
        report_rows.append({"round_id": round_id, "node_id": report.node_id,
                            "sha256_before": digest(old["report"]), "sha256_after": digest(current["report"]),
                            "unchanged": old["report"] == current["report"],
                            "schema_ids_valid": report.round_id == round_id and report.node_id == current["node_id"],
                            "report_accepted": bool(current["report_accepted"]), "evidence_characters": len(report.evidence)})
    checks["all_four_reports_unchanged_valid_accepted"] = len(report_rows) == 4 and all(
        r["unchanged"] and r["schema_ids_valid"] and r["report_accepted"] for r in report_rows)
    checks["original_two_parent_rows_unchanged"] = len(old_pairs) == 2 and all(pairs.get(k) == v for k, v in old_pairs.items())
    pair_rows = []
    for round_id, row in pairs.items():
        response = ParentRoundResponse.model_validate_json(row["payload"])
        current, next_round = rounds[round_id], rounds[row["next_round_id"]]
        report_event, parent_event = event_id("report_stored", round_id), event_id("parent_response_stored", round_id)
        next_prompt_event, next_dispatch = event_id("prompt_stored", next_round["id"]), event_id("leaf_dispatched", next_round["id"])
        valid = (response.responding_to_round_id == round_id and response.child_node_id == current["node_id"]
                 and row["parent_id"] == "root" and next_round["node_id"] == current["node_id"]
                 and next_round["previous_round_id"] == round_id and next_round["task"] == response.next_prompt)
        ordered = (report_event is not None and parent_event is not None and next_prompt_event is not None
                   and report_event < next_prompt_event < parent_event and (next_dispatch is None or parent_event < next_dispatch))
        pair_rows.append({"round_id": round_id, "next_round_id": next_round["id"], "schema_and_exact_links_valid": valid,
                          "next_prompt_characters": len(response.next_prompt), "next_prompt_words": len(response.next_prompt.split()),
                          "next_prompt_sha256": digest(response.next_prompt), "report_event": report_event,
                          "next_prompt_saved_event": next_prompt_event, "parent_response_saved_event": parent_event,
                          "next_dispatch_event": next_dispatch, "protocol_order_valid": ordered})
    checks["four_complete_linked_pairs"] = len(pair_rows) == 4 and all(p["schema_and_exact_links_valid"] for p in pair_rows)
    checks["report_next_prompt_parent_commit_precede_next_dispatch"] = all(p["protocol_order_valid"] for p in pair_rows)
    old_leaf = {t["id"]: t for t in before["turns"] if t["id"].startswith("leaf:")}
    leaf = {t["id"]: t for t in after["turns"] if t["id"].startswith("leaf:")}
    checks["entire_leaf_turn_set_unchanged"] = leaf == old_leaf and len(leaf) == 4
    third_ids = {r["id"] for r in rounds.values() if r["number"] >= 3}
    checks["no_round3_leaf_turn_or_dispatch"] = not any(
        t["id"].startswith("leaf:" + round_id + ":") for t in after["turns"] for round_id in third_ids
    ) and not any(e["type"] == "leaf_dispatched" and e["decoded"].get("round_id") in third_ids for e in events)
    stable_fields = ("id", "parent_id", "goal", "relative_weight")
    topology = lambda data: sorted(tuple(n[k] for k in stable_fields) for n in data["nodes"])
    checks["same_three_node_topology_goals_weights"] = len(after["nodes"]) == 3 and topology(before) == topology(after)
    settings = lambda data: {r["key"]: json.loads(r["value"]) for r in data["settings"]}
    old_settings, current_settings = settings(before), settings(after)
    cfg = Config.model_validate(current_settings["config"])
    checks["saved_config_and_review_setting_unchanged"] = (old_settings["config"] == current_settings["config"]
        and old_settings["manual_review_enabled"] == current_settings["manual_review_enabled"])
    before_approvals = {a["id"]: a for a in before["approvals"]}
    approvals = {a["id"]: a for a in after["approvals"]}
    checks["all_preexisting_approval_rows_unchanged"] = all(approvals.get(k) == v for k, v in before_approvals.items())
    artifact_map = {(a["round_id"], a["artifact_type"], a["version"]): a for a in after["artifacts"]}
    checks["all_approval_hashes_match_saved_artifacts"] = all(
        (a["round_id"], a["artifact_type"], a["version"]) in artifact_map
        and a["content_hash"] == digest(a["payload"])
        and artifact_map[(a["round_id"], a["artifact_type"], a["version"])]["content_hash"] == a["content_hash"]
        and artifact_map[(a["round_id"], a["artifact_type"], a["version"])]["payload"] == a["payload"] for a in approvals.values())
    old_conversations = {s["id"]: s["bridge_session_id"] for s in before["sessions"]}
    checks["same_original_conversations"] = all(sessions.get(k, {}).get("bridge_session_id") == v for k, v in old_conversations.items())
    completed_parents = [t for t in after["turns"] if t["id"].startswith("parent:") and t["status"] == "COMPLETED"]
    checks["four_successful_parent_turns"] = len(completed_parents) == 4
    nodes = {n["id"]: n for n in after["nodes"]}
    prompt_checks = []
    for turn in completed_parents:
        context = json.loads(turn["prompt"].rsplit("\nCONTEXT_JSON\n", 1)[1].split("\nOUTPUT_SCHEMA_JSON\n", 1)[0])
        report = rounds[context["round_id"]]
        prompt_checks.append({"turn_id": turn["id"], "round_id": report["id"],
            "entire_current_report_identical": context["report"] == json.loads(report["report"]),
            "exact_ids_and_goals": context["node_id"] == "root" and context["child_node_id"] == report["node_id"]
                and context["goal"] == nodes["root"]["goal"] and context["child_goal"] == nodes[report["node_id"]]["goal"]})
    checks["successful_parent_prompts_preserve_full_current_report_ids_goals"] = all(
        p["entire_current_report_identical"] and p["exact_ids_and_goals"] for p in prompt_checks)
    defaults = Config()
    checks["production_role_defaults_preserved"] = PRO_MODEL == "GPT-6 Pro" and PARENT_MODEL == "GPT-6 Extra High" and defaults.bridge_pro_model == "GPT-6 Pro" and defaults.bridge_parent_model == "GPT-6 Thinking" and defaults.bridge_parent_effort == "xhigh"
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "reports": report_rows,
            "parent_pairs": pair_rows, "parent_prompt_checks": prompt_checks, "leaf_turn_ids_unchanged": sorted(leaf),
            "successful_parent_turns": [{"id": t["id"], "request_id": t["bridge_request_id"], "prompt_characters": len(t["prompt"]),
                "conversation_id": sessions[t["session_id"]]["bridge_session_id"], "stored_model": sessions[t["session_id"]]["model"]} for t in completed_parents],
            "review_and_capacity": {"manual_review_enabled": current_settings["manual_review_enabled"],
                "max_active_leaves": cfg.max_active_leaves, "max_concurrent_pro_turns": cfg.max_concurrent_pro_turns,
                "current_leaf_statuses": {n["id"]: n["status"] for n in after["nodes"] if n["parent_id"]},
                "production_default_roles": {"parent": PARENT_MODEL, "leaf": PRO_MODEL},
                "live_override": "Existing experiment uses Extra High for all three nodes; production Pro default retained."},
            "limitations": ["Read-only saved-record audit; exact live model pre/post selection and Send evidence remain in request evidence files.",
                "Manual review was disabled in this disposable baseline; this audit verifies unchanged saved controls and approval hashes, not a new human-approval interaction.",
                "No additional leaf inference occurred; both round-3 prompts are saved for future work but undispatched."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="20261015-long-prompt")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    run = BASE / "runs" / args.run
    before_path = run / "snapshots/tree_before.db"
    current_path = BASE / "runs/20261014-live-r2/projects/tree/tree.db"
    result = {"at": datetime.now(UTC).isoformat(), "run_id": args.run,
              "scope": "SQLite URI mode=ro, query_only transactions; no Store initialization, browser, or HTTP calls.",
              "snapshot_sha256": hashlib.sha256(before_path.read_bytes()).hexdigest(),
              **audit(snapshot(before_path), snapshot(current_path))}
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
