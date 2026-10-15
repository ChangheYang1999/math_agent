#!/usr/bin/env python3
"""Capped, disposable live tree. Only explicit commands can contact the bridge."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "bridge_xhigh_live"))
sys.path.insert(0, str(HERE.parents[1] / "src"))
from run_experiment import (  # noqa: E402
    COORDINATOR_MODEL,
    Config,
    ExperimentScheduler,
    Harness,
    LiveBridge,
    Paths,
    Store,
    redact,
    stamp,
)

from math_research_agent.schemas import LeafRoundReport, ParentRoundResponse  # noqa: E402
from math_research_agent.store import digest  # noqa: E402

FLAG = "TEST_ONLY_EXTRA_HIGH_LEAF_OVERRIDE"
NOTICE = (
    FLAG + ": This disposable experiment uses actual GPT-6 / Extra High for this leaf. "
    "It is not GPT-6 Pro inference. Preserve the research protocol and exact report IDs.\n\n"
)
GOAL = (
    FLAG + ". Study the sharp endpoint-zero discrete path Poincare inequality: for "
    "each integer N >= 2 and real x_0=x_N=0, determine the optimal constant C_N in "
    "sum_{j=1}^{N-1} x_j^2 <= C_N sum_{j=0}^{N-1}(x_{j+1}-x_j)^2, its equality "
    "cases, and a rigorous stability estimate for near extremizers. Make a genuine "
    "two-task decomposition: one complementary spectral eigenvalue/equality/stability "
    "investigation, one elementary finite-sum bound and independent sharpness/boundary "
    "verification investigation. Propose exactly two useful children with positive "
    "weights summing to one; available capacity four is only an upper bound. Plan "
    "three meaningful successive rounds per child, refining proofs and checking "
    "degeneracies rather than repeating a solved statement. Each round returns one "
    "concise complete report; aim below 1200 words while retaining essential proofs. "
    "Do not require external data or software execution. All experimental leaves "
    "actually use GPT-6 Extra High; never claim Pro or independent verification."
)


class ExperimentStore(Store):
    def create_round(self, node_id, task, previous_round_id=None, kind="research", c=None):
        if c is None:
            with self.transaction() as connection:
                return self.create_round(node_id, task, previous_round_id, kind, connection)
        round_id = super().create_round(node_id, task, previous_round_id, kind, c)
        row = c.execute("SELECT * FROM rounds WHERE id=?", (round_id,)).fetchone()
        # Preserve the generated original as history, then save an honest distinct
        # version whose exact hash is the one checked by production dispatch.
        prompt = NOTICE + row["prompt"].replace(
            "You are one persistent GPT-6 Pro research leaf.",
            "You are one persistent GPT-6 Extra High experimental research leaf.",
        )
        version = row["prompt_version"] + 1
        c.execute(
            "UPDATE approvals SET status='SUPERSEDED' WHERE round_id=? AND artifact_type='prompt'",
            (round_id,),
        )
        review = self.artifact(c, node_id, round_id, "prompt", prompt, version)
        c.execute(
            "UPDATE rounds SET prompt=?,prompt_version=?,stage=? WHERE id=?",
            (prompt, version, "PROMPT_APPROVAL" if review else "PROMPT_READY", round_id),
        )
        self.event(
            "experiment_model_override",
            {
                "round_id": round_id,
                "flag": FLAG,
                "old_hash": digest(row["prompt"]),
                "content_hash": digest(prompt),
                "version": version,
            },
            c,
        )
        return round_id


class CappedBridge(LiveBridge):
    async def _json(self, method, path, **kwargs):
        if method == "POST" and path == "/turns":
            self.harness.reserve(kwargs["json"])
        return await super()._json(method, path, **kwargs)

    async def send_message(self, session, prompt, turn_id):
        try:
            return await super().send_message(session, prompt, turn_id)
        except Exception as exc:
            self.harness.halt(str(exc), turn_id)
            raise

    async def await_response(self, session, turn_id):
        done = asyncio.Event()

        async def watch_uncertainty():
            request_id = self.store.one(
                "SELECT bridge_request_id FROM turns WHERE id=?", (turn_id,)
            )["bridge_request_id"]
            while request_id and not done.is_set():
                try:
                    events = await self._json(
                        "GET", f"/turns/{request_id}/events", params={"limit": 5000}
                    )
                    if any(
                        "submit.uncertain" in event.get("type", "")
                        or "request.effect.uncertain" in event.get("type", "")
                        for event in events.get("events", [])
                    ):
                        self.harness.halt(
                            "Post-Send uncertainty observed; preserve this exact request without replay",
                            turn_id,
                        )
                        return
                except Exception as exc:
                    self.harness.halt("Own-request observation failed: " + str(exc), turn_id)
                    return
                try:
                    await asyncio.wait_for(done.wait(), timeout=2)
                except TimeoutError:
                    pass

        watcher = asyncio.create_task(watch_uncertainty())
        try:
            return await super().await_response(session, turn_id)
        except Exception as exc:
            self.harness.halt(str(exc), turn_id)
            raise
        finally:
            done.set()
            await watcher


class BoundedScheduler(ExperimentScheduler):
    async def _request(self, *args, **kwargs):
        if args[2] == "parent_bootstrap":
            prior = kwargs.get("validate")

            def validate(out):
                if prior:
                    prior(out)
                if len(out.children) != 2:
                    raise ValueError("Bounded experiment requires exactly two useful tasks")

            kwargs["validate"] = validate
        return await super()._request(*args, **kwargs)

    async def _coordinate(self, actor_id, context, key, message_id=None):
        self.store.event(
            "experiment_optional_conversation_deferred",
            {
                "actor_id": actor_id,
                "key": key,
                "reason": "Protect the bounded mandatory-cycle budget",
            },
        )
        self.store.set_setting("optional_error:" + key, True)


class Phase3(Harness):
    def __init__(self):
        self.root = HERE / "runs/live"
        self.root.mkdir(parents=True, exist_ok=True)
        self.files, self.bridges = Paths(self.root), {}
        path = self.root / "manifest.json"
        self.data = (
            json.loads(path.read_text())
            if path.exists()
            else {
                "run_id": "phase3-live",
                "nonce": uuid4().hex,
                "created": stamp(),
                "live_or_mock": "live",
                "flag": FLAG,
                "actual_model_label": "GPT-6",
                "browser_instance": "Existing Chrome/profile only; root verifies UI identity",
                "sessions": {"tree": {}},
                "measurements": {},
                "attempts": {},
                "phases": {},
            }
        )
        if self.data.get("flag") != FLAG or self.data.get("actual_model_label") != "GPT-6":
            raise ValueError("Saved experiment identity/configuration mismatch")
        self.save()

    def bridge(self, group="tree"):
        if group != "tree":
            raise ValueError("This experiment has one isolated tree only")
        if group not in self.bridges:
            path = self.root / "project"
            if (path / "tree.db").exists():
                store = ExperimentStore(path)
            else:
                store = ExperimentStore.initialize(
                    path,
                    GOAL,
                    Config(
                        transport="bridge",
                        manual_review_enabled=False,
                        max_active_leaves=4,
                        max_concurrent_pro_turns=2,
                        format_retries=0,
                        bridge_parent_model="GPT-6",
                        bridge_parent_effort="xhigh",
                        bridge_turn_timeout=900,
                        projects_root=self.root,
                    ),
                )
                store.set_setting("experiment_model_override", FLAG)
            if (
                store.config.manual_review_enabled
                or store.config.format_retries != 0
                or store.config.bridge_parent_model != "GPT-6"
                or store.setting("experiment_model_override") != FLAG
            ):
                raise ValueError("Disposable experiment settings changed; no dispatch permitted")
            self.bridges[group] = CappedBridge(store, self, group)
        return self.bridges[group]

    def halt(self, reason, turn_id):
        self.data.setdefault("halt", {**stamp(), "reason": reason, "turn_id": turn_id})
        self.save()

    def reserve(self, body):
        if self.data.get("halt"):
            raise ValueError("Experiment halted; no new submissions permitted")
        ledger_path = HERE / "request_ledger.json"
        with (HERE / ".request-budget.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            ledger = (
                json.loads(ledger_path.read_text())
                if ledger_path.exists()
                else {
                    "hard_cap": 16,
                    "requests": [],
                }
            )
            if ledger.get("hard_cap") != 16 or len(ledger["requests"]) >= 16:
                raise ValueError("Phase 3 hard cap reached; no new request sent")
            if any(row["request_id"] == body["id"] for row in ledger["requests"]):
                raise ValueError(
                    "Request already reserved; recover its exact durable ID, never POST again"
                )
            ledger["requests"].append(
                {
                    **stamp(),
                    "request_id": body["id"],
                    "run_nonce": self.data["nonce"],
                    "characters": len(body["message"]),
                    "sha256": digest(body["message"]),
                    "source_client_id": body["sourceClientId"],
                    "session_id": body["sessionId"],
                    "required_model": body["metadata"]["requiredModel"],
                    "required_effort": body["metadata"]["requiredEffort"],
                    "reservation": "Before POST; never refunded after uncertain delivery",
                }
            )
            Paths(HERE).atomic_write("request_ledger.json", json.dumps(ledger, indent=2) + "\n")

    def scheduler(self):
        scheduler = BoundedScheduler(self.bridge().store, self.bridge())
        scheduler.experiment_rounds_per_leaf = 3
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
            frozen = sorted(nodes.values())
            if self.data.setdefault("frozen_nodes", frozen) != frozen:
                raise ValueError("Experiment topology changed; no new conversation permitted")
        for label, node_id in nodes.items():
            session = await bridge.create_session(
                node_id, COORDINATOR_MODEL, f"phase3:{self.data['nonce']}:{node_id}"
            )
            self.data["sessions"]["tree"][label] = self.binding(bridge, session.id)
            self.save()
        return self.group("tree")

    async def bootstrap(self):
        await self.verify("tree")
        scheduler = self.scheduler()
        try:
            scheduler._acquire()
            if scheduler.store.children("root"):
                return {"already_bootstrapped": True}
            await scheduler._bootstrap()
            return {"children": scheduler.store.children("root")}
        finally:
            await scheduler.aclose()
            await self.export()

    async def idle(self, resume=False):
        bridge = self.bridge()
        health = await bridge._json("GET", "/health")
        if (
            health.get("activeRequests")
            or health.get("pendingRequests")
            or health.get("pendingCommands")
        ):
            raise ValueError("Bridge is not idle; no restart/reconciliation exercise permitted")
        if bridge.store.one(
            "SELECT id FROM turns WHERE raw_response IS NULL AND status!='FAILED_NOT_SENT'"
        ):
            raise ValueError("Own durable turn remains unresolved; preserve it without restart")
        tables = {}
        for name in ("nodes", "sessions", "turns", "rounds", "parent_responses", "approvals"):
            rows = bridge.store.query(f"SELECT * FROM {name}")
            tables[name] = digest(
                json.dumps(
                    sorted(rows, key=lambda r: json.dumps(r, sort_keys=True)), sort_keys=True
                )
            )
        snapshot = {**stamp(), "tables": tables, "zero_bridge_work": True}
        if resume:
            before = json.loads(self.files.read("idle_before_restart.json"))
            snapshot["same_saved_state"] = tables == before["tables"]
            if not snapshot["same_saved_state"]:
                raise ValueError("Idle restart changed durable identities or gates")
            self.files.write_immutable(
                "idle_after_restart.json", json.dumps(snapshot, indent=2) + "\n"
            )
        else:
            self.files.write_immutable(
                "idle_before_restart.json", json.dumps(snapshot, indent=2) + "\n"
            )
            with sqlite3.connect(bridge.store.path.as_uri() + "?mode=ro", uri=True) as source:
                destination = self.root / "idle_before_restart.db"
                with destination.open("xb"):
                    pass
                with sqlite3.connect(destination) as target:
                    source.backup(target)
        return snapshot

    async def run(self):
        if self.data.get("halt"):
            raise ValueError("Experiment halted; preserve and reconcile the recorded exact turn")
        await self.verify("tree")
        if len(self.data.get("frozen_nodes", [])) != 3:
            raise ValueError("Prepare and freeze exactly three independent conversations first")
        scheduler = self.scheduler()
        scheduler._baseline = 0
        scheduler._max_pairs = 6
        done, own_ids = asyncio.Event(), set()

        async def watch():
            while not done.is_set():
                own_ids.update(
                    row["bridge_request_id"]
                    for row in scheduler.store.query(
                        "SELECT bridge_request_id FROM turns WHERE bridge_request_id IS NOT NULL"
                    )
                )
                await asyncio.sleep(0.2)

        watcher = asyncio.create_task(watch())
        observer = asyncio.create_task(self.observe("tree", done, own_ids, "three-round-tree"))
        try:
            while True:
                errors = scheduler.store.query("SELECT * FROM errors WHERE resolved=0")
                if errors:
                    self.halt(
                        "A protocol/transport error requires explicit reconciliation",
                        errors[0]["operation"],
                    )
                if self.data.get("halt"):
                    # Already dispatched requests may finish and save their evidence;
                    # reserve() blocks every further POST, including other parents.
                    await asyncio.gather(*scheduler._tasks.values(), return_exceptions=True)
                    raise ValueError(
                        "Stopped with durable unresolved/error state; no request replayed"
                    )
                elif scheduler.store.one("SELECT id FROM approvals WHERE status='PENDING'"):
                    self.halt("WAITING_FOR_HUMAN", "approval")
                elif scheduler.store.one("SELECT COUNT(*) AS n FROM parent_responses")["n"] >= 6:
                    break
                else:
                    await scheduler.tick()
                await asyncio.sleep(0.1)
            for job in scheduler.store.query(
                "SELECT * FROM optional_jobs WHERE status='PENDING' ORDER BY priority,created_at,id"
            ):
                try:
                    scheduler._local_optional(job)
                except Exception as exc:
                    scheduler.store.execute(
                        "UPDATE optional_jobs SET status='ERROR',error=? WHERE id=?",
                        (str(exc), job["id"]),
                    )
            scheduler.store.build_report()
        finally:
            done.set()
            await asyncio.gather(watcher, observer)
            await scheduler.aclose()
            await self.export()
        return {"completed_pairs": 6, "flag": FLAG}

    async def export(self):
        bridge = self.bridge()
        store = bridge.store
        events = store.query("SELECT * FROM events ORDER BY id")
        parsed_events = [{**row, "payload": json.loads(row["payload"])} for row in events]
        evidence_errors = []
        for turn in store.query("SELECT * FROM turns ORDER BY created_at,id"):
            try:
                evidence = await self.own_evidence(bridge, turn["id"])
            except Exception as exc:
                evidence_errors.append({"turn_id": turn["id"], "error": str(exc)})
                continue
            prompt_hash = digest(turn["prompt"])
            confirmations = [
                e
                for e in evidence.get("events", [])
                if e.get("type") == "diagnostic.chat.prompt.submit.confirmed"
            ]
            full_text = any(
                (payload := event.get("data", {}).get("payload", {})).get("fullPromptTextMatch")
                is True
                and payload.get("expectedSha256") == prompt_hash
                and payload.get("observedSha256") == prompt_hash
                and payload.get("observedCharacters") == len(turn["prompt"])
                for event in confirmations
            )
            session = store.one("SELECT * FROM sessions WHERE id=?", (turn["session_id"],))
            timing = self.data["measurements"].get(turn["bridge_request_id"], {})
            self.data["attempts"][turn["id"]] = {
                "phase": "tree",
                "label": session["node_id"],
                "started": timing.get("dispatch_started", stamp()),
                "request_id": turn["bridge_request_id"],
                "terminal_status": turn["status"],
                "upstream_status": (evidence.get("turn") or {}).get("status"),
                "upstream_completed_at": (evidence.get("turn") or {}).get("completedAt"),
                "characters": len(turn["prompt"]),
                "sha256": prompt_hash,
                "full_submitted_text_verified": full_text,
                "binding": self.binding(bridge, session["id"]),
            }
        pairs = []
        for row in store.query("SELECT * FROM parent_responses ORDER BY created_at,round_id"):
            round_ = store.one("SELECT * FROM rounds WHERE id=?", (row["round_id"],))
            report = LeafRoundReport.model_validate_json(round_["report"])
            response = ParentRoundResponse.model_validate_json(row["payload"])
            report_event = next(
                e["id"]
                for e in parsed_events
                if e["type"] == "report_stored" and e["payload"]["round_id"] == row["round_id"]
            )
            parent_event = next(
                e["id"]
                for e in parsed_events
                if e["type"] == "parent_response_stored"
                and e["payload"]["round_id"] == row["round_id"]
            )
            next_dispatch = next(
                (
                    e["id"]
                    for e in parsed_events
                    if e["type"] == "leaf_dispatched"
                    and e["payload"]["round_id"] == row["next_round_id"]
                ),
                None,
            )
            pairs.append(
                {
                    "round_id": row["round_id"],
                    "next_round_id": row["next_round_id"],
                    "links_valid": report.node_id == response.child_node_id == round_["node_id"]
                    and report.round_id == response.responding_to_round_id == round_["id"],
                    "report_hash": digest(round_["report"]),
                    "parent_hash": digest(row["payload"]),
                    "report_event": report_event,
                    "parent_event": parent_event,
                    "next_dispatch_event": next_dispatch,
                    "mandatory_order": report_event < parent_event
                    and (next_dispatch is None or parent_event < next_dispatch),
                }
            )
        for _label, session in self.group("tree").items():
            session.update(self.binding(bridge, session["id"]))
        self.data["phases"]["completed_pairs"] = len(pairs)
        self.data["phases"]["six_pairs_valid"] = len(pairs) == 6 and all(
            p["links_valid"] and p["mandatory_order"] for p in pairs
        )
        summary = {
            **stamp(),
            "flag": FLAG,
            "pairs": pairs,
            "evidence_errors": evidence_errors,
            "allocation": store.allocation(),
            "rounds": store.query("SELECT * FROM rounds ORDER BY seq"),
            "parent_responses": store.query("SELECT * FROM parent_responses"),
            "events": parsed_events,
            "errors": store.query("SELECT * FROM errors"),
            "optional_jobs": store.query("SELECT * FROM optional_jobs"),
            "sessions": self.group("tree"),
        }
        self.files.atomic_write("tree_summary.json", json.dumps(redact(summary), indent=2) + "\n")
        self.save()
        return {"completed_pairs": len(pairs), "evidence_errors": evidence_errors}


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
            "run",
            "status",
            "export",
            "idle",
            "resumeidle",
        ),
    )
    args = parser.parse_args()
    harness = Phase3()
    # All commands/processes share one runner lock in this disposable project.
    lock = (harness.root / ".command.lock").open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == "init":
            harness.bridge()
            result = {
                "manifest": str(harness.root / "manifest.json"),
                "nonce": harness.data["nonce"],
                "flag": FLAG,
            }
        elif args.command in ("preparebootstrap", "preparetree"):
            result = await harness.prepare(args.command == "preparetree")
        elif args.command == "verify":
            result = await harness.verify("tree")
        elif args.command in ("idle", "resumeidle"):
            result = await harness.idle(args.command == "resumeidle")
        elif args.command == "status":
            result = harness.data
        else:
            result = await getattr(harness, args.command)()
        print(json.dumps(redact(result), indent=2))
        return 0
    except Exception as exc:
        harness.data.setdefault("command_errors", []).append(
            {**stamp(), "command": args.command, "error": str(exc)}
        )
        harness.save()
        print(
            json.dumps(
                {"error": str(exc), "manifest": str(harness.root / "manifest.json")}, indent=2
            )
        )
        return 1
    finally:
        lock.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
