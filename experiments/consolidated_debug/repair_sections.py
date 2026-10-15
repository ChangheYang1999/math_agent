"""Explicit zero-inference repair of this experiment's deferred-publication order."""

import hashlib
import json
import sqlite3
from pathlib import Path

from math_research_agent.store import digest


def _snapshot(store):
    names = [
        row["name"]
        for row in store.query("SELECT name FROM sqlite_master WHERE type='table'")
        if row["name"] not in {"sections", "events", "settings", "sqlite_sequence"}
    ]
    return {
        "tables": {name: store.query(f'SELECT * FROM "{name}" ORDER BY rowid') for name in names},
        "settings": store.query("SELECT * FROM settings WHERE key!='report_dirty' ORDER BY key"),
    }


def repair_latest_sections(store, backup_path):
    """Append exact latest saved owner payloads; retain all old rows and P0 data."""
    if "CONSOLIDATED_GENUINE_PRO_TREE" not in store.node("root")["goal"]:
        raise ValueError("Only the isolated genuine-Pro experiment may use this repair")
    if store.one("SELECT COUNT(*) n FROM parent_responses")["n"] != 6:
        raise ValueError("Six completed pairs are required before report publication")
    if store.one("SELECT COUNT(*) n FROM turns WHERE status IN ('PENDING','SENT')")["n"]:
        raise ValueError("An in-flight turn prevents publication repair")
    jobs = store.query(
        "SELECT rowid AS original_rowid,* FROM optional_jobs WHERE kind='section' ORDER BY rowid"
    )
    if not jobs or any(job["status"] != "COMPLETED" for job in jobs):
        raise ValueError("All original section jobs must already be completed")
    latest = {job["actor_id"]: job for job in jobs}
    changes = []
    for actor, job in latest.items():
        payload = json.loads(job["payload"])
        if payload["node_id"] != actor:
            raise ValueError("Saved section owner mismatch")
        current = store.one(
            "SELECT * FROM sections WHERE node_id=? ORDER BY version DESC LIMIT 1", (actor,)
        )
        fields = ("body", "claim_status", "evidence_reference", "independent_verification")
        if not current or any(current[key] != payload.get(key, "") for key in fields):
            changes.append((actor, job, payload))
    if not changes:
        return {"already_current": True, "new_inference_requests": 0, "changed_nodes": []}
    before, sections = _snapshot(store), store.query("SELECT * FROM sections ORDER BY id")
    backup_path = Path(backup_path)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.open("xb").close()
    with sqlite3.connect(store.path) as source, sqlite3.connect(backup_path) as target:
        source.backup(target)
    for actor, _job, payload in changes:
        store.update_section(actor, payload)
    if (
        _snapshot(store) != before
        or store.query(
            "SELECT * FROM sections WHERE id<=? ORDER BY id",
            (sections[-1]["id"] if sections else 0,),
        )
        != sections
    ):
        raise RuntimeError("Publication repair changed original source data")
    receipt = {
        "backup": str(backup_path.resolve()),
        "backup_sha256": hashlib.sha256(backup_path.read_bytes()).hexdigest(),
        "new_inference_requests": 0,
        "changed_nodes": [actor for actor, _, _ in changes],
        "sources": [
            {
                "actor_id": actor,
                "job_id": job["id"],
                "original_rowid": job["original_rowid"],
                "payload_sha256": digest(job["payload"]),
            }
            for actor, job, _ in changes
        ],
        "source_tables_unchanged": True,
        "original_sections_unchanged": True,
    }
    store.event("experiment_report_publication_repaired", receipt)
    store.build_report()
    return receipt
