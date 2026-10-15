"""Lossless current reports and session-aware durable context for parent decisions."""

from __future__ import annotations

import json

from .schemas import PARENT_MODEL, PRO_MODEL


def compact_schema(schema):
    """Drop display titles, retaining every JSON Schema validation constraint."""
    if isinstance(schema, dict):
        return {
            key: compact_schema(value)
            for key, value in schema.items()
            if key != "title" or not isinstance(value, str)
        }
    if isinstance(schema, list):
        return [compact_schema(value) for value in schema]
    return schema


def parent_context(store, context, session):
    """Reuse a persistent parent's history; restore complete history for a new chat.

    No report or proof is shortened. Only duplicated prior assessments are replaced
    by references when a committed parent turn proves this conversation has history.
    """
    result = dict(context)
    history = store.query(
        "SELECT r.id,r.node_id,r.report,r.report_accepted,p.payload,p.source FROM parent_responses p "
        "JOIN rounds r ON r.id=p.round_id WHERE p.parent_id=? AND r.id!=? ORDER BY r.seq",
        (context["node_id"], context["round_id"]),
    )
    seen = store.query(
        "SELECT t.prompt FROM turns t JOIN parent_responses p "
        "ON t.id LIKE 'parent:' || p.round_id || ':e%' "
        "WHERE t.session_id=? AND t.status='COMPLETED' AND t.raw_response IS NOT NULL "
        "AND p.parent_id=?",
        (session.id, context["node_id"]),
    )
    try:
        state = json.loads(context.get("research_state") or "{}").copy()
    except (ValueError, AttributeError):
        state = {"summary": context.get("research_state", "")}
    if not isinstance(state, dict):
        state = {"summary": context.get("research_state", "")}
    reports = {row["id"]: json.loads(row["report"]) for row in history}
    known = set()
    for turn in seen:
        try:
            prior = json.loads(
                turn["prompt"]
                .rsplit("\nCONTEXT_JSON\n", 1)[1]
                .split("\nOUTPUT_SCHEMA_JSON\n", 1)[0]
            )
        except (ValueError, IndexError):
            continue
        if not isinstance(prior, dict):
            continue
        candidates = [prior.get("report")] + [
            item.get("report")
            for item in prior.get("restored_history", [])
            if isinstance(item, dict)
        ]
        for report in candidates:
            if (
                isinstance(report, dict)
                and report.get("round_id") in reports
                and report == reports[report["round_id"]]
            ):
                known.add(report["round_id"])
    missing = [row for row in history if row["id"] not in known]
    latest = {}
    for row in history:
        report = reports[row["id"]]
        latest[row["node_id"]] = {
            "node_id": row["node_id"],
            "round_id": row["id"],
            "status": report["status"],
            "summary": report["summary"],
            "report_accepted": bool(row["report_accepted"]),
            "response_source": row["source"],
        }
    if seen:
        result["research_state"] = {
            key: value for key, value in state.items() if key != "child_assessments"
        }
        result["prior_report_references"] = list(latest.values())
        result["conversation_context"] = (
            "Persistent parent conversation; prior complete reports and decisions remain in this chat. Any missing durable history is restored below."
        )
    else:
        result["research_state"] = state
        result["conversation_context"] = (
            "New or replaced parent conversation; complete durable prior reports and decisions are restored below."
        )
    if missing:
        result["restored_history"] = [
            {
                "report": reports[row["id"]],
                "report_accepted": bool(row["report_accepted"]),
                "response_source": row["source"],
                "parent_response": json.loads(row["payload"]),
            }
            for row in missing
        ]
    models = {
        row["node_id"]: row["model"]
        for row in store.query("SELECT node_id,model FROM sessions WHERE active=1")
    }
    result["model_roles"] = {
        "parent": session.model,
        "child": models.get(context["child_node_id"], PRO_MODEL),
        "production_parent_default": PARENT_MODEL,
        "production_leaf_default": PRO_MODEL,
    }
    result["review"] = {
        "manual_review_enabled": store.setting("manual_review_enabled", False),
        "current_report_accepted": bool(
            store.one("SELECT report_accepted FROM rounds WHERE id=?", (context["round_id"],))[
                "report_accepted"
            ]
        ),
    }
    result["inbound_internal_messages"] = [
        {
            key: message[key]
            for key in ("id", "sender_node_id", "message", "evidence_reference", "reason")
        }
        for message in context.get("inbound_internal_messages", [])
    ]
    return result
