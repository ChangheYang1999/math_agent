#!/usr/bin/env python3
"""Bounded genuine-Pro tree; root alone runs explicit live commands."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import importlib.util
import json
import sys
from pathlib import Path
from uuid import uuid4

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))
FLAG = "CONSOLIDATED_GENUINE_PRO_TREE"

# Reuse generic measurement, export, idle and observation code in a private
# module instance. Its artifact label changes in memory only; no historical
# source/data changes, and neither its experimental Store nor scheduler is used.
spec = importlib.util.spec_from_file_location(
    "_consolidated_measurement_helpers", HERE.parent / "phase3/run_live.py"
)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
helpers.FLAG = FLAG

from math_research_agent.config import Config  # noqa: E402
from math_research_agent.paths import Paths  # noqa: E402
from math_research_agent.scheduler import Scheduler  # noqa: E402
from math_research_agent.store import Store, digest  # noqa: E402
from math_research_agent.transport import COORDINATOR_MODEL, PRO_MODEL  # noqa: E402

GOAL = (
    FLAG + ". Investigate the sharp cyclic mean-zero discrete Poincare inequality. "
    "For every integer N >= 3 and real cyclic sequence x_0,...,x_{N-1} with "
    "sum_j x_j=0 and x_N=x_0, determine the optimal C_N in "
    "sum_j x_j^2 <= C_N sum_j (x_{j+1}-x_j)^2, characterize its real equality "
    "space, and prove a quantitative near-extremizer stability theorem. "
    "Propose exactly two useful complementary tasks with positive weights summing "
    "to one: a DFT/eigenvalue/equality investigation and an elementary finite-sum "
    "or trigonometric-correlation verification with boundary and sharpness audits. "
    "Capacity four is an upper bound; create only these two mathematically useful "
    "leaves. Their research conversations use actual GPT-6 Pro; the coordinator "
    "uses actual GPT-6 Extra High. Plan three successive research rounds per child: "
    "first establish the sharp inequality and full two-dimensional real equality "
    "space; second derive deficit-to-distance stability with precise normalization; "
    "third audit optimal constants, near-extremizers and degeneracies. Treat N=3 "
    "and N=4 explicitly; do not invoke a nonexistent complementary spectral gap "
    "when the equality space is the entire mean-zero space. The elementary branch "
    "must distinguish independent finite-sum arguments from restated spectral "
    "arguments. Authorize only one initial round per child, then assess each exact "
    "report and save its next concrete task. Return concise complete reports, "
    "aiming around 700 words while preserving essential proof. No external data "
    "or software execution. Do not claim independent verification."
)


class BoundedProScheduler(Scheduler):
    async def _session(self, node_id, model):
        if node_id not in self.experiment_nodes:
            raise ValueError("Frozen genuine-Pro topology forbids another conversation")
        expected = COORDINATOR_MODEL if node_id == "root" else PRO_MODEL
        if model != expected:
            raise ValueError("Genuine tree role cannot be replaced by another model")
        return await super()._session(node_id, model)

    async def _request(self, *args, **kwargs):
        if args[2] == "parent_bootstrap":
            previous = kwargs.get("validate")

            def validate(output):
                if previous:
                    previous(output)
                if len(output.children) != 2:
                    raise ValueError("Bounded bootstrap requires exactly two useful children")

            kwargs["validate"] = validate
        return await super()._request(*args, **kwargs)

    async def _leaf(self, round_id):
        row = self.store.one("SELECT * FROM rounds WHERE id=?", (round_id,))
        if row["number"] > 3:
            raise ValueError("Three-round leaf limit reached; no message sent")
        await super()._leaf(round_id)
        row = self.store.one("SELECT * FROM rounds WHERE id=?", (round_id,))
        if row["number"] == 3 and row["report"]:
            self.store.set_node_status(row["node_id"], "PAUSED")

    def _local_optional(self, job):
        if job["kind"] in {"tree", "message"}:
            status = "DEFERRED_EXPERIMENT"
        elif job["kind"] == "section":
            status = "DEFERRED_UNTIL_SIX_PAIRS"
        else:
            return super()._local_optional(job)
        self.store.execute("UPDATE optional_jobs SET status=? WHERE id=?", (status, job["id"]))
        self.store.event("bounded_optional_deferred", {"job_id": job["id"], "status": status})

    async def _coordinate(self, actor_id, context, key, message_id=None):
        self.store.event("bounded_coordination_deferred", {"actor_id": actor_id, "key": key})
        self.store.set_setting("optional_error:" + key, True)


class Consolidated(helpers.Phase3):
    def __init__(self):
        self.root = HERE / "runs/pro_tree"
        self.root.mkdir(parents=True, exist_ok=True)
        self.files, self.bridges = Paths(self.root), {}
        path = self.root / "manifest.json"
        self.data = (
            json.loads(path.read_text())
            if path.exists()
            else {
                "run_id": "consolidated-pro-tree",
                "nonce": uuid4().hex,
                "created": helpers.stamp(),
                "live_or_mock": "live",
                "flag": FLAG,
                "actual_model_label": "GPT-6",
                "browser_instance": "Existing Chrome/profile; exact role/tier selected in owned tabs",
                "sessions": {"tree": {}},
                "measurements": {},
                "attempts": {},
                "phases": {},
            }
        )
        if self.data.get("flag") != FLAG:
            raise ValueError("Saved experiment label mismatch")
        self.save()

    def bridge(self, group="tree"):
        if group != "tree":
            raise ValueError("Only the new isolated genuine-Pro tree is permitted")
        if group not in self.bridges:
            path = self.root / "project"
            if (path / "tree.db").exists():
                store = Store(path)
            else:
                store = Store.initialize(
                    path,
                    GOAL,
                    Config(
                        transport="bridge",
                        manual_review_enabled=False,
                        max_active_leaves=4,
                        max_concurrent_pro_turns=2,
                        format_retries=0,
                        bridge_turn_timeout=1200,
                        projects_root=self.root,
                    ),
                )
                store.set_setting("experiment_label", FLAG)
            if (
                store.config.format_retries != 0
                or store.config.bridge_pro_model != "GPT-6 Pro"
                or store.config.bridge_parent_model != "GPT-6 Thinking"
                or store.setting("experiment_label") != FLAG
            ):
                raise ValueError("Genuine production roles or bounded settings changed")
            self.bridges[group] = helpers.CappedBridge(store, self, group)
        return self.bridges[group]

    def reserve(self, body):
        if self.data.get("halt"):
            raise ValueError("Halted experiment cannot submit another request")
        with (HERE / ".request-budget.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            path = HERE / "request_ledger.json"
            ledger = (
                json.loads(path.read_text()) if path.exists() else {"hard_cap": 16, "requests": []}
            )
            if ledger.get("hard_cap") != 16 or len(ledger["requests"]) >= 16:
                raise ValueError("Consolidated global cap16 reached; no POST sent")
            if any(row["request_id"] == body["id"] for row in ledger["requests"]):
                raise ValueError(
                    "Reserved request must be reconciled by its original ID; no repeated POST"
                )
            ledger["requests"].append(
                {
                    **helpers.stamp(),
                    "request_id": body["id"],
                    "run_nonce": self.data["nonce"],
                    "characters": len(body["message"]),
                    "sha256": digest(body["message"]),
                    "source_client_id": body["sourceClientId"],
                    "session_id": body["sessionId"],
                    "required_model": body["metadata"]["requiredModel"],
                    "required_effort": body["metadata"]["requiredEffort"],
                    "reservation": "Before POST; never refunded after uncertainty",
                }
            )
            Paths(HERE).atomic_write("request_ledger.json", json.dumps(ledger, indent=2) + "\n")

    def scheduler(self):
        scheduler = BoundedProScheduler(self.bridge().store, self.bridge())
        scheduler.experiment_nodes = set(self.data.get("frozen_nodes", ["root"]))
        return scheduler

    async def prepare(self, tree=False):
        bridge = self.bridge()
        nodes = {"Parent": "root"}
        if tree:
            children = bridge.store.children("root")
            if len(children) != 2:
                raise ValueError("Complete the actual two-child bootstrap before preparetree")
            nodes.update({f"Leaf-{i + 1}": node["id"] for i, node in enumerate(children)})
            if self.data.setdefault("frozen_nodes", sorted(nodes.values())) != sorted(
                nodes.values()
            ):
                raise ValueError("Saved topology changed; no new session permitted")
        for label, node_id in nodes.items():
            model = COORDINATOR_MODEL if node_id == "root" else PRO_MODEL
            session = await bridge.create_session(
                node_id, model, f"{self.data['nonce']}:{node_id}:{model}"
            )
            self.data["sessions"]["tree"][label] = self.binding(bridge, session.id)
            self.save()
        return self.group("tree")

    async def smoke(self):
        await self.verify("tree")
        if len(self.data.get("frozen_nodes", [])) != 3:
            raise ValueError("Bind and positively verify Parent plus both Pro leaves first")
        scheduler = self.scheduler()
        if scheduler.store.one("SELECT id FROM approvals WHERE status='PENDING'"):
            raise ValueError("WAITING_FOR_HUMAN: exact prompt approval remains pending")
        node = self.group("tree")["Leaf-1"]["node_id"]
        row = scheduler.store.one("SELECT * FROM rounds WHERE node_id=? AND number=1", (node,))
        key = "leaf:" + row["id"]
        if scheduler.store.one("SELECT id FROM turns WHERE id LIKE ?", (key + ":e%",)):
            raise ValueError("Smoke already attempted; preserve its exact ID without retry")
        try:
            scheduler._acquire()
            await scheduler._leaf(row["id"])
            current = scheduler.store.one("SELECT * FROM rounds WHERE id=?", (row["id"],))
            self.data["phases"]["pro_smoke"] = {
                "round_id": row["id"],
                "report_sha256": digest(current["report"]),
                "mandatory_parent_pending": current["stage"] == "AWAITING_PARENT_RESPONSE",
                "scope": "First genuine Pro leaf round; included in six-pair target, not an extra request",
            }
            self.save()
            return self.data["phases"]["pro_smoke"]
        except Exception as exc:
            self.halt(str(exc), key)
            raise
        finally:
            await scheduler.aclose()
            await self.export()

    async def resume_recovered_smoke(self):
        """Explicit zero-Send checkpoint after the known Pro capture failure."""
        from math_research_agent.leaf_recovery import RECEIPT, validate_leaf_recovery

        if self.data.get("resume_verified_leaf_recovery"):
            return self.data["resume_verified_leaf_recovery"]
        bridge = self.bridge()
        turn_id = "leaf:n-3790f8503746-r000001:e0:a0"
        proof = json.loads((HERE / "pro_smoke_recovery_proof.json").read_text())
        _, receipt = validate_leaf_recovery(bridge.store, turn_id, proof)
        saved = bridge.store.query("SELECT payload FROM events WHERE type=?", (RECEIPT,))
        if not any(json.loads(row["payload"]) == receipt for row in saved):
            raise ValueError("The exact audited Leaf recovery is not committed")
        halt = self.data.get("halt") or {}
        if halt.get("turn_id") != turn_id.rsplit(":e", 1)[0] or not halt.get(
            "reason", ""
        ).startswith("Format repair exhausted"):
            raise ValueError("This resume only reconciles the known original capture failure")
        if bridge.store.query("SELECT id FROM errors WHERE resolved=0"):
            raise ValueError("Unresolved errors still require reconciliation")
        await self.verify("tree")
        for turn in bridge.store.query("SELECT * FROM turns"):
            remote = await bridge._json("GET", "/turns/" + turn["bridge_request_id"])
            if remote["turn"]["status"] != "completed":
                raise ValueError("A submitted request is not terminal; no resume permitted")
        checkpoint = self.root / "halted_before_pro_recovery.json"
        if checkpoint.exists():
            previous = json.loads(checkpoint.read_text())
            if previous.get("nonce") != self.data["nonce"] or previous.get("halt") != halt:
                raise ValueError("Existing halt checkpoint belongs to different recovery")
        else:
            self.files.write_immutable(
                "halted_before_pro_recovery.json", json.dumps(self.data, indent=2) + "\n"
            )
        for row in bridge.store.query("SELECT * FROM rounds WHERE stage='PROMPT_READY'"):
            if "single fenced JSON code block" not in row["prompt"]:
                if bridge.store.one(
                    "SELECT id FROM turns WHERE id LIKE ?", ("leaf:" + row["id"] + ":%",)
                ):
                    raise ValueError("An already attempted prompt cannot be revised")
                bridge.store.revise_prompt(row["id"], row["task"])
                bridge.store.event(
                    "experiment_output_format_revision",
                    {
                        "round_id": row["id"],
                        "reason": "Preserve literal JSON mathematics in a fenced code block",
                    },
                )
        resumed = {
            **helpers.stamp(),
            "receipt": receipt,
            "previous_halt": halt,
            "new_inference_requests": 0,
        }
        bridge.store.event("experiment_resume_after_leaf_recovery", resumed)
        self.data.setdefault("halt_history", []).append(halt)
        del self.data["halt"]
        self.data["resume_verified_leaf_recovery"] = resumed
        self.data["phases"]["pro_smoke"] = {
            "round_id": receipt["round_id"],
            "status": "GENUINE_PRO_FINAL_RECOVERED",
            "original_capture": "INVALID reasoning recap preserved",
            "mandatory_parent_pending": True,
        }
        self.save()
        return resumed

    async def resume_recovered_round1(self):
        """Explicit zero-Send release of only the two source-reconciled failures."""
        from math_research_agent.recovery import unresolved_turns

        if self.data.get("resume_verified_round1"):
            return self.data["resume_verified_round1"]
        bridge = self.bridge()
        store = bridge.store
        expected = {
            "leaf:n-dab935ae44d1-r000001": "leaf_recovery_committed",
            "parent:n-3790f8503746-r000001": "parent_recovery_committed",
        }
        errors = store.query("SELECT * FROM errors WHERE resolved=0 ORDER BY id")
        if len(errors) != 2 or {row["operation"] for row in errors} != set(expected):
            raise ValueError("Only the two exact recorded round-one failures may resume")
        receipts = []
        for operation, kind in expected.items():
            turn_id = operation + ":e0:a0"
            turn = store.one("SELECT * FROM turns WHERE id=?", (turn_id,))
            matches = [
                json.loads(row["payload"])
                for row in store.query("SELECT payload FROM events WHERE type=?", (kind,))
                if json.loads(row["payload"]).get("turn_id") == turn_id
            ]
            if len(matches) != 1 or not turn or turn["status"] != "ERROR":
                raise ValueError("The exact audited recovery receipt is missing")
            remote = await bridge._json("GET", "/turns/" + turn["bridge_request_id"])
            if remote["turn"]["status"] != "failed":
                raise ValueError("The original failed terminal must remain unchanged")
            receipts.append(matches[0])
        if unresolved_turns(store):
            raise ValueError("An unsettled exact turn still prevents resumption")
        halt = self.data.get("halt")
        if not halt or halt.get("turn_id") != "leaf:n-dab935ae44d1-r000001:e0:a0":
            raise ValueError("The current halt is not the reconciled Leaf2 failure")
        await self.verify("tree")
        self.files.write_immutable(
            "halted_before_round1_recovery.json", json.dumps(self.data, indent=2) + "\n"
        )
        scheduler = self.scheduler()
        scheduler._acquire()
        try:
            with store.transaction() as connection:
                for error in errors:
                    connection.execute("UPDATE errors SET resolved=1 WHERE id=?", (error["id"],))
                    connection.execute(
                        "UPDATE nodes SET runtime_state='OK' WHERE id=? AND runtime_state='ERROR'",
                        (error["node_id"],),
                    )
                resumed = {
                    **helpers.stamp(),
                    "previous_halt": halt,
                    "receipts": receipts,
                    "errors_released": errors,
                    "new_inference_requests": 0,
                }
                store.event("experiment_resume_after_round1_recovery", resumed, connection)
            for row in store.query("SELECT * FROM rounds WHERE stage='PROMPT_READY'"):
                if "single fenced JSON code block" not in row["prompt"]:
                    if store.one(
                        "SELECT id FROM turns WHERE id LIKE ?", ("leaf:" + row["id"] + ":%",)
                    ):
                        raise ValueError("An already attempted prompt cannot be revised")
                    store.revise_prompt(row["id"], row["task"])
            self.data.setdefault("halt_history", []).append(halt)
            del self.data["halt"]
            self.data["resume_verified_round1"] = resumed
            self.save()
            return resumed
        finally:
            await scheduler.aclose()

    async def resume_after_busy(self):
        """Explicitly retry only a source-proven undelivered turn in a fresh client."""
        from math_research_agent.recovery import unresolved_turns

        bridge = self.bridge()
        store = bridge.store
        turn_id = "leaf:n-dab935ae44d1-r000002:e0:a0"
        operation = turn_id.rsplit(":e", 1)[0]
        turn = store.one("SELECT * FROM turns WHERE id=?", (turn_id,))
        errors = store.query("SELECT * FROM errors WHERE resolved=0 ORDER BY id")
        if (
            not turn
            or turn["status"] != "FAILED_NOT_SENT"
            or len(errors) != 1
            or errors[0]["operation"] != operation
            or unresolved_turns(store)
        ):
            raise ValueError("Only the exact proven undelivered busy attempt may resume")
        halt = self.data.get("halt")
        if not halt or halt.get("turn_id") != turn_id:
            raise ValueError("The current halt is not this undelivered attempt")
        saved = self.data["sessions"]["tree"]["Leaf-2"]
        old_binding = dict(saved)
        clients = (await bridge._json("GET", "/browser/clients"))["clients"]
        if any(c["id"] == saved["bridge_client_id"] for c in clients):
            raise ValueError("Close only the completed stale owned tab before rebinding")
        await bridge._json(
            "POST",
            "/browser/select",
            json={"clientId": self.group("tree")["Parent"]["bridge_client_id"]},
        )
        await bridge.recover_session(turn["session_id"])
        new_binding = self.binding(bridge, turn["session_id"])
        if (
            new_binding["bridge_session_id"] != saved["bridge_session_id"]
            or new_binding["id"] != saved["id"]
            or new_binding["bridge_client_id"] == saved["bridge_client_id"]
        ):
            raise ValueError("Recovery must retain the exact durable session and conversation")
        self.data["sessions"]["tree"]["Leaf-2"] = new_binding
        self.save()
        await self.verify("tree")
        self.files.write_immutable(
            "halted_before_busy_recovery.json", json.dumps(self.data, indent=2) + "\n"
        )
        scheduler = self.scheduler()
        scheduler._acquire()
        try:
            if store.setting("retry:" + operation, 0) != 0:
                raise ValueError("An explicit replacement attempt was already authorized")
            with store.transaction() as connection:
                connection.execute(
                    "INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    ("retry:" + operation, "1"),
                )
                connection.execute("UPDATE errors SET resolved=1 WHERE id=?", (errors[0]["id"],))
                connection.execute(
                    "UPDATE nodes SET runtime_state='OK' WHERE id=? AND runtime_state='ERROR'",
                    (errors[0]["node_id"],),
                )
                resumed = {
                    **helpers.stamp(),
                    "previous_halt": halt,
                    "old_binding": old_binding,
                    "new_binding": new_binding,
                    "proven_not_sent_turn": turn,
                    "released_error": errors[0],
                    "new_inference_requests": 0,
                }
                store.event("experiment_resume_after_proven_busy_rejection", resumed, connection)
            self.data.setdefault("halt_history", []).append(halt)
            del self.data["halt"]
            self.data["resume_verified_busy_recovery"] = resumed
            self.save()
            return resumed
        finally:
            await scheduler.aclose()

    async def resume_after_rich_recovery(self):
        """Release only the audited third-round source recovery; never resend it."""
        from math_research_agent.recovery import unresolved_turns

        bridge = self.bridge()
        store = bridge.store
        turn_id = "leaf:n-3790f8503746-r000003:e0:a0"
        errors = store.query("SELECT * FROM errors WHERE resolved=0 ORDER BY id")
        halt = self.data.get("halt")
        receipts = [
            json.loads(row["payload"])
            for row in store.query(
                "SELECT payload FROM events WHERE type='leaf_recovery_committed'"
            )
            if json.loads(row["payload"]).get("turn_id") == turn_id
        ]
        if (
            len(receipts) != 1
            or unresolved_turns(store)
            or len(errors) != 1
            or errors[0]["operation"] != turn_id.rsplit(":e", 1)[0]
            or not halt
            or halt.get("turn_id") != turn_id
            or store.node("n-3790f8503746")["status"] != "PAUSED"
        ):
            raise ValueError("Only the exact committed third-round recovery may resume")
        remote = await bridge._json("GET", "/turns/" + receipts[0]["request_id"])
        if (
            remote["turn"]["status"] != "failed"
            or remote["turn"]["error"]["code"] != "CANONICAL_DEADLINE_EXCEEDED"
        ):
            raise ValueError("The original failed terminal must remain intact")
        await self.verify("tree")
        clients = (await bridge._json("GET", "/browser/clients"))["clients"]
        own = {entry["bridge_client_id"] for entry in self.group("tree").values()}
        if any(c.get("activeRequest") for c in clients if c["id"] in own):
            raise ValueError("An owned browser lease still needs cleanup")
        self.files.write_immutable(
            "halted_before_rich_recovery.json", json.dumps(self.data, indent=2) + "\n"
        )
        scheduler = self.scheduler()
        scheduler._acquire()
        try:
            with store.transaction() as connection:
                connection.execute("UPDATE errors SET resolved=1 WHERE id=?", (errors[0]["id"],))
                connection.execute(
                    "UPDATE nodes SET runtime_state='OK' WHERE id=? AND runtime_state='ERROR'",
                    (errors[0]["node_id"],),
                )
                resumed = {
                    **helpers.stamp(),
                    "previous_halt": halt,
                    "receipt": receipts[0],
                    "released_error": errors[0],
                    "new_inference_requests": 0,
                    "third_round_leaf_remains_paused": True,
                }
                store.event("experiment_resume_after_rich_user_recovery", resumed, connection)
            self.data.setdefault("halt_history", []).append(halt)
            del self.data["halt"]
            self.data["resume_verified_rich_recovery"] = resumed
            self.save()
            return resumed
        finally:
            await scheduler.aclose()

    async def run(self):
        result = await super().run()
        scheduler = self.scheduler()
        for job in scheduler.store.query(
            "SELECT * FROM optional_jobs WHERE status='DEFERRED_UNTIL_SIX_PAIRS' ORDER BY rowid"
        ):
            try:
                Scheduler._local_optional(scheduler, job)
            except Exception as exc:
                scheduler.store.execute(
                    "UPDATE optional_jobs SET status='ERROR',error=? WHERE id=?",
                    (str(exc), job["id"]),
                )
        scheduler.store.build_report()
        await self.export()
        return result


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "init",
            "preparebootstrap",
            "bootstrap",
            "preparetree",
            "verify",
            "smoke",
            "run",
            "export",
            "status",
            "idle",
            "resumeidle",
            "resume_recovered_smoke",
            "resume_recovered_round1",
            "resume_after_busy",
            "resume_after_rich_recovery",
        ),
    )
    args = parser.parse_args()
    harness = Consolidated()
    with (harness.root / ".command.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.command == "init":
                harness.bridge()
                result = {"manifest": str(harness.root / "manifest.json"), "flag": FLAG}
            elif args.command in {"preparebootstrap", "preparetree"}:
                result = await harness.prepare(args.command == "preparetree")
            elif args.command == "verify":
                result = await harness.verify("tree")
            elif args.command in {"idle", "resumeidle"}:
                result = await harness.idle(args.command == "resumeidle")
            elif args.command == "status":
                result = harness.data
            else:
                result = await getattr(harness, args.command)()
            print(json.dumps(helpers.redact(result), indent=2))
            return 0
        except Exception as exc:
            harness.data.setdefault("command_errors", []).append(
                {**helpers.stamp(), "command": args.command, "error": str(exc)}
            )
            harness.save()
            print(
                json.dumps(
                    {"error": str(exc), "manifest": str(harness.root / "manifest.json")}, indent=2
                )
            )
            return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
