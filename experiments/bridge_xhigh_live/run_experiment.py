#!/usr/bin/env python3
"""Bounded, resumable live experiment; never starts a browser or supplies replies."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlparse
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from math_research_agent.bridge_transport import BridgeTransport  # noqa: E402
from math_research_agent.config import Config  # noqa: E402
from math_research_agent.paths import Paths  # noqa: E402
from math_research_agent.scheduler import Scheduler  # noqa: E402
from math_research_agent.store import Store  # noqa: E402
from math_research_agent.transport import COORDINATOR_MODEL, PRO_MODEL  # noqa: E402

BASE = Path(__file__).resolve().parent
PROCESS_ID = uuid4().hex
MARKERS = {"A": "TREE-A-719", "B": "TREE-B-284", "C": "TREE-C-563"}
SMOKE = (
    "You are Session A. Your fixed marker is TREE-A-719. Calculate 37 * 43, "
    "explain in one or two sentences, and include your fixed marker in the final response."
)
SMOKE_CONTEXT = "What was your fixed marker in our previous exchange? Answer in one sentence."
PROMPTS = {
    "A": "You are Session A. Your fixed marker is TREE-A-719. Derive and explain the identity 1+3+...+(2n-1)=n^2 in a clear proof. End your response with TREE-A-719.",
    "B": "You are Session B. Your fixed marker is TREE-B-284. Give a rigorous proof that sqrt(2) is irrational and point out the crucial parity step. End your response with TREE-B-284.",
    "C": "You are Session C. Your fixed marker is TREE-C-563. Prove that every finite tree with at least two vertices has at least two leaves. End your response with TREE-C-563.",
}
CONTEXT = (
    "What was your original fixed marker, and what mathematical task did you solve in our "
    "previous exchange? Answer with your marker and a one-sentence summary."
)


def stamp():
    return {"at": datetime.now(UTC).isoformat(), "monotonic_ns": time.monotonic_ns(),
            "process_id": PROCESS_ID}


def redact(value):
    """Last-resort redaction; request headers and credentials are never collected."""
    if isinstance(value, dict):
        return {
            key: redact(item)
            for key, item in value.items()
            if not re.search(r"token|authorization|cookie|password|secret|leaseId", key, re.I)
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        token = os.environ.get("MATHAGENT_BRIDGE_API_TOKEN", "")
        return value.replace(token, "[REDACTED]") if token else value
    return value


def epoch(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def generation_overlap(samples, request_ids, measurements, completed_at):
    """Intersect bounded observations; a cached active flag alone proves nothing."""
    intervals = {}
    for request_id in sorted(request_ids):
        timing = measurements.get(request_id, {})
        spans, previous = [], None
        if not (timing.get("dispatch_started") and timing.get("terminal_record_received")):
            intervals[request_id] = spans
            continue
        start = epoch(timing["dispatch_started"]["at"])
        end = epoch(timing["terminal_record_received"]["at"])
        if completed_at.get(request_id):
            end = min(end, epoch(completed_at[request_id]))
        for sample in samples:
            tab = next((t for t in sample.get("tabs", []) if t.get("request_id") == request_id), {})
            observed = float(tab.get("observed_at") or 0) / 1000
            if not (tab.get("fresh") and tab.get("own_request")
                    and (tab.get("generation") or {}).get("state") == "active"
                    and start <= observed <= end):
                previous = None
                continue
            if previous == observed:
                continue  # Repeated cached telemetry cannot create an interval.
            if previous is not None and 0 < observed - previous <= 2:
                if spans and spans[-1][1] == previous:
                    spans[-1][1] = observed
                else:
                    spans.append([previous, observed])
            previous = observed
        intervals[request_id] = spans
    shared = [[float("-inf"), float("inf")]]
    for spans in intervals.values():
        shared = [[max(a, c), min(b, d)] for a, b in shared for c, d in spans
                  if max(a, c) < min(b, d)]
    seconds = sum(end - start for start, end in shared) if intervals else 0
    return {
        "request_ids": sorted(request_ids), "activity_intervals_epoch_seconds": intervals,
        "shared_intervals_epoch_seconds": shared if intervals else [],
        "observed_overlap_seconds": seconds,
        "limitation": "Activity between consecutive active observations is inferred at <=2s resolution. "
        "Cached single observations, >2s gaps, and observations outside dispatch/terminal bounds "
        "do not establish concurrency. Brief transitions between samples remain unobservable.",
    }


class LiveBridge(BridgeTransport):
    """Production adapter plus measurement, with no change to selection or replies."""

    def __init__(self, store, harness, label):
        super().__init__(store)
        if urlparse(self.base_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Live experiment permits only a loopback bridge URL")
        self.harness, self.label = harness, label
        self.measured_client = None

    async def _json(self, method, path, **kwargs):
        request_id = kwargs.get("json", {}).get("id") if path == "/turns" else None
        if method == "POST" and request_id:
            self.harness.measure(request_id, "dispatch_started", stamp())
        result = await super()._json(method, path, **kwargs)
        if method == "POST" and path == "/browser/select":
            self.measured_client = kwargs.get("json", {}).get("clientId")
        if method == "GET" and path in {"/models", "/efforts"}:
            self.harness.data.setdefault("selection_checks", []).append({
                **stamp(), "group": self.label, "client_id": self.measured_client,
                "kind": path.removeprefix("/"), "current": result.get("current"),
                "options": result.get(path.removeprefix("/")),
            })
            self.harness.save()
        if method == "POST" and request_id:
            self.harness.measure(request_id, "dispatch_acknowledged", stamp())
        return result

    async def _terminal(self, session, turn_id, upstream):
        if upstream.get("status") in {
            "completed", "completed_without_artifact", "failed", "interrupted", "cancelled"
        }:
            self.harness.measure(upstream["id"], "terminal_record_received", stamp())
        raw = await super()._terminal(session, turn_id, upstream)
        if raw is not None:
            self.harness.measure(upstream["id"], "terminal_accepted", stamp())
        return raw


class ExperimentScheduler(Scheduler):
    """Extra High leaves in this disposable driver only; production stays Pro."""

    async def _session(self, node_id, model):
        if node_id not in self.experiment_nodes:
            raise ValueError("Experiment topology is frozen; no conversation may be added")
        return await super()._session(
            node_id, COORDINATOR_MODEL if model == PRO_MODEL else model
        )

    async def _leaf(self, round_id):
        planned = self.store.one("SELECT * FROM rounds WHERE id=?", (round_id,))
        if planned["number"] > self.experiment_rounds_per_leaf:
            raise ValueError("Experiment per-leaf dispatch bound reached; no message sent")
        await super()._leaf(round_id)
        round_record = self.store.one("SELECT * FROM rounds WHERE id=?", (round_id,))
        if round_record["number"] >= self.experiment_rounds_per_leaf:
            # Pause only the disposable leaf after saving its report. P0 still
            # completes its parent's response, without starting an extra turn.
            self.store.set_node_status(round_record["node_id"], "PAUSED")

    def _local_optional(self, job):
        if job["kind"] in {"tree", "message"}:
            self.store.execute("UPDATE optional_jobs SET status='DEFERRED_EXPERIMENT' WHERE id=?", (job["id"],))
            self.store.event("experiment_control_deferred", {"job_id": job["id"], "kind": job["kind"]})
            return
        return super()._local_optional(job)


class Harness:
    def __init__(self, args):
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", args.run):
            raise ValueError("Run ID must be 1-80 letters, digits, underscores or hyphens")
        self.args = args
        self.root = BASE / "runs" / args.run
        self.root.mkdir(parents=True, exist_ok=True)
        self.files = Paths(self.root)
        self.bridges = {}
        manifest = self.root / "manifest.json"
        self.data = json.loads(manifest.read_text()) if manifest.exists() else {
            "run_id": args.run,
            "created": stamp(),
            "live_or_mock": "live",
            "actual_model_label": args.actual_model_label,
            "browser_instance": args.browser_instance or "Existing browser; verify Phase 0 evidence",
            "sessions": {},
            "measurements": {},
            "attempts": {},
            "phases": {},
        }
        saved_label = self.data.get("actual_model_label", "GPT-6 Thinking")
        if saved_label != args.actual_model_label:
            raise ValueError(
                f"Run requires its saved exact model label {saved_label!r}; "
                "a changed --actual-model-label is not permitted on resume"
            )
        self.data["actual_model_label"] = saved_label
        self.save()

    def save(self):
        self.files.atomic_write("manifest.json", json.dumps(redact(self.data), indent=2) + "\n")
        rows = []
        for attempt in self.data.get("attempts", {}).values():
            binding = attempt.get("binding", {})
            prepared = self.data["sessions"].get(attempt["phase"], {}).get(attempt["label"], {})
            measurement = self.data["measurements"].get(attempt.get("request_id"), {})
            rows.append({
                "phase": attempt["phase"], "live_or_mock": "live",
                "actual_model": binding.get("bridge_model"),
                "actual_effort": binding.get("bridge_effort"),
                "browser_instance": self.data["browser_instance"],
                "tab_id": prepared.get("browser_tab_id") or binding.get("bridge_client_id"),
                "conversation_id": binding.get("bridge_session_id"),
                "turn/request_id": attempt.get("request_id"),
                "started_at": measurement.get("dispatch_started", attempt["started"])["at"],
                "finished_at": measurement.get("terminal_record_received", attempt.get("finished", {})).get("at"),
                "terminal_status": attempt.get("terminal_status", "PREPARING"),
                "correct_marker": attempt.get("correct_marker"),
                "context_retained": attempt.get("context_retained"),
            })
        self.files.atomic_write("results_rows.json", json.dumps(redact(rows), indent=2) + "\n")

    def measure(self, request_id, key, value):
        # Preserve original dispatch times when resuming the same durable turn.
        self.data["measurements"].setdefault(request_id, {}).setdefault(key, value)
        self.save()

    def bridge(self, group):
        if group in self.bridges:
            return self.bridges[group]
        path = self.root / "projects" / ("tree" if group == "tree" else "bridge-test")
        if (path / "tree.db").exists():
            store = Store(path)
            if store.config.bridge_parent_model != self.data["actual_model_label"]:
                raise ValueError("Disposable database model label differs from the saved run manifest")
        else:
            store = Store.initialize(
                path,
                "Live disposable experiment: independently prove the odd-number sum identity "
                "and the irrationality of sqrt(2), retaining rigorous evidence and boundaries.",
                Config(transport="bridge", max_active_leaves=2, max_concurrent_pro_turns=2,
                       manual_review_enabled=False, format_retries=1, bridge_turn_timeout=1800,
                       bridge_parent_model=self.data["actual_model_label"]),
            )
        self.bridges[group] = LiveBridge(store, self, group)
        return self.bridges[group]

    def group(self, name):
        sessions = self.data["sessions"].get(name)
        if not sessions:
            raise ValueError(f"Run prepare --group {name} first; this command creates no tabs")
        return sessions

    def confirmed_capacity_failure(self):
        attempts = [self.data["attempts"].get(f"parallel-{label}-proof", {}) for label in "ABC"]
        if any(a.get("upstream_status") not in {"completed", "completed_without_artifact", "failed"}
               for a in attempts):
            raise ValueError("Two-request probe requires all three original requests authoritatively terminal")
        if any(a.get("upstream_status") != "failed" and a.get("terminal_status") != "COMPLETED"
               for a in attempts):
            raise ValueError("Unverified/uncertain replies must be reconciled before any two-request probe")
        pattern = r"rate.?limit|too many (?:concurrent )?requests|concurren\w*.{0,35}(?:limit|maximum)|(?:limit|maximum).{0,35}concurren|(?:reached|exceeded).{0,35}(?:usage |message )?limit|capacity.{0,20}(?:exceeded|unavailable)"
        failures = [a for a in attempts if a.get("upstream_status") == "failed"
                    and re.search(pattern, json.dumps(a.get("upstream_error") or {}), re.I)]
        if not failures:
            raise ValueError("No explicit authoritative capacity failure; no fallback messages permitted")
        return [a["request_id"] for a in failures]

    async def prepare(self, group):
        if group == "two":
            self.confirmed_capacity_failure()
        bridge = self.bridge(group)
        if group == "tree":
            if not self.data["phases"].get("phase2_pass"):
                raise ValueError("Tree preparation requires passing parallel and context tests")
            if not bridge.store.children("root"):
                bridge.store.split("root", [
                    {"goal": "Prove the sum of the first n odd positive integers is n squared.",
                     "relative_weight": .5,
                     "initial_prompt": "For every integer n >= 1, rigorously prove 1+3+...+(2n-1)=n^2. Explain induction and check n=1; report the proof and its hypotheses."},
                    {"goal": "Prove that the square root of two is irrational.",
                     "relative_weight": .5,
                     "initial_prompt": "Give a rigorous contradiction proof that sqrt(2) is irrational. Start from coprime integers p,q with q nonzero and p^2=2q^2; justify both parity inferences and the contradiction."},
                ], actor_id="root")
                bridge.store.set_setting("coordinator_ready:root", True)
            nodes = {"Parent": "root", **{
                f"Leaf-{i+1}": node["id"]
                for i, node in enumerate(bridge.store.children("root"))
            }}
        else:
            letters = "A" if group == "smoke" else "AB" if group == "two" else "ABC"
            nodes = {letter: f"{group}-{letter}" for letter in letters}
        group_data = self.data["sessions"].setdefault(group, {})
        for label, node_id in nodes.items():
            session = await bridge.create_session(node_id, COORDINATOR_MODEL, f"{self.args.run}:{node_id}")
            group_data[label] = self.binding(bridge, session.id)
            self.save()
        return group_data

    def binding(self, bridge, session_id):
        row = bridge.store.one("SELECT * FROM sessions WHERE id=?", (session_id,))
        return {key: row[key] for key in (
            "id", "node_id", "model", "url", "bridge_client_id", "bridge_session_id",
            "bridge_model", "bridge_effort", "bridge_state",
        )}

    async def verify(self, group):
        bridge = self.bridge(group)
        clients = (await bridge._json("GET", "/browser/clients")).get("clients", [])
        # A reload temporarily disconnects content scripts. Verification must
        # not turn that transient gap into a replacement tab in this experiment.
        for entry in self.group(group).values():
            saved = self.binding(bridge, entry["id"])
            if not any(c.get("id") == saved["bridge_client_id"] for c in clients):
                raise ValueError("Saved experiment tab is disconnected; reconnect that exact tab before verification")
        for label, entry in self.group(group).items():
            session = bridge.get_session(entry["id"])
            await bridge._selection(session)
            updated = self.binding(bridge, session.id)
            client = next((c for c in clients if c["id"] == updated["bridge_client_id"]), {})
            updated["browser_tab_id"] = client.get("browserTabId")
            updated["verified_at"] = stamp()
            self.data["sessions"][group][label] = updated
            self.save()
        ids = [s["bridge_client_id"] for s in self.group(group).values()]
        if len(ids) != len(set(ids)):
            raise ValueError("Experiment sessions do not have distinct browser clients")
        return self.group(group)

    async def own_evidence(self, bridge, turn_id):
        local = bridge.store.one("SELECT * FROM turns WHERE id=?", (turn_id,))
        if not local or not local["bridge_request_id"]:
            return {"local_status": local["status"] if local else "NOT_DISPATCHED"}
        request_id = local["bridge_request_id"]
        remote = await bridge._json("GET", "/turns/" + quote(request_id, safe=""))
        events = await bridge._json("GET", "/turns/" + quote(request_id, safe="") + "/events", params={"limit": 5000})
        result = {
            "live_or_mock": "live", "local_turn_id": turn_id, "local_status": local["status"],
            "request_id": request_id, "turn": remote.get("turn"), "events": events.get("events", []),
            "events_limit": 5000, "events_may_be_truncated": len(events.get("events", [])) >= 5000,
            "measurements": self.data["measurements"].get(request_id, {}),
        }
        self.files.atomic_write(f"evidence/{turn_id}.json", json.dumps(redact(result), indent=2) + "\n")
        return result

    async def turn(self, group, label, name, prompt, context=False):
        bridge = self.bridge(group)
        session = bridge.get_session(self.group(group)[label]["id"])
        turn_id = f"{group}-{label}-{name}"
        attempt = self.data["attempts"].setdefault(turn_id, {
            "phase": group, "label": label, "live_or_mock": "live", "turn_id": turn_id,
            "started": stamp(), "prompt": prompt,
        })
        before = self.binding(bridge, session.id)
        self.save()
        try:
            await bridge.send_message(session, prompt, turn_id)
            answer = await bridge.await_response(session, turn_id)
            binding = self.binding(bridge, session.id)
            correct = MARKERS[label] in answer and not any(
                marker in answer for other, marker in MARKERS.items() if other != label
            )
            lower = answer.casefold()
            addresses_task = (
                any(word in lower for word in ("odd", "sum", "n^2", "n²", "n^{2}"))
                if label == "A" else "irrational" in lower
                if label == "B" else "tree" in lower and "lea" in lower
            ) if group in {"parallel", "two"} else bool(re.search(r"\b1,?591\b", answer)) if not context else True
            attempt.update(
                answer=answer, terminal_status="COMPLETED", correct_marker=correct,
                addresses_task=addresses_task,
                binding=binding, context_retained=(
                    correct and bool(before["bridge_session_id"])
                    and before["bridge_session_id"] == binding["bridge_session_id"]
                    and before["url"] == binding["url"]
                ) if context else None,
            )
            attempt.pop("error", None)
            attempt.pop("evidence_error", None)
            self.data["sessions"][group][label].update(binding)
        except Exception as exc:
            attempt.update(terminal_status="ERROR_OR_UNCERTAIN", error=str(exc))
        finally:
            attempt["finished"] = stamp()
            try:
                evidence = await self.own_evidence(bridge, turn_id)
                attempt["request_id"] = evidence.get("request_id")
                attempt["upstream_status"] = (evidence.get("turn") or {}).get("status")
                attempt["upstream_error"] = (evidence.get("turn") or {}).get("error")
                attempt["upstream_completed_at"] = (evidence.get("turn") or {}).get("completedAt")
            except Exception as exc:
                attempt["evidence_error"] = str(exc)
            self.save()
        return attempt

    async def observe(self, group, done, request_ids, batch):
        """Only retain experimental tab metadata, never unrelated browser content."""
        bridge = self.bridge(group)
        own = {s["bridge_client_id"] for s in self.group(group).values()}
        samples = self.data.setdefault("generation_samples", {}).setdefault(group, [])
        while not done.is_set():
            at = stamp()
            sample = {**at, "batch": batch, "tabs": []}
            try:
                clients = (await bridge._json("GET", "/browser/clients")).get("clients", [])
                for client in clients:
                    if client.get("id") not in own:
                        continue
                    observation = client.get("tabObservation") or {}
                    active = client.get("activeRequest") or {}
                    observed_at = observation.get("observedAt", 0)
                    age = time.time() * 1000 - float(observed_at or 0)
                    sample["tabs"].append({
                        "client_id": client["id"], "tab_id": client.get("browserTabId"),
                        "request_id": active.get("requestId"), "observed_at": observed_at,
                        "generation": observation.get("generation"),
                        "fresh": 0 <= age <= 5000,
                        "own_request": active.get("requestId") in request_ids,
                    })
                sample["cached_active_clients"] = [
                    tab["client_id"] for tab in sample["tabs"]
                    if tab["fresh"] and tab["own_request"]
                    and (tab["generation"] or {}).get("state") == "active"
                ]
            except Exception as exc:
                sample["error"] = str(exc)
            samples.append(sample)
            self.save()
            try:
                await asyncio.wait_for(done.wait(), timeout=.75)
            except TimeoutError:
                pass

    async def simultaneous(self, group, name, prompts, context=False):
        await self.verify(group)  # Fail before *any* message if a tab is misconfigured.
        bridge = self.bridge(group)
        request_ids = {bridge._request_id(f"{group}-{label}-{name}") for label in prompts}
        done = asyncio.Event()
        observer = asyncio.create_task(self.observe(group, done, request_ids, name))
        try:
            return await asyncio.gather(*(
                self.turn(group, label, name, prompt, context=context)
                for label, prompt in prompts.items()
            ))
        finally:
            done.set()
            await observer

    def overlap(self, attempts):
        measurements = [self.data["measurements"].get(a.get("request_id"), {}) for a in attempts]
        if any(not (m.get("dispatch_started") and m.get("terminal_record_received")) for m in measurements):
            return None
        processes = {
            m[key].get("process_id") for m in measurements
            for key in ("dispatch_started", "terminal_record_received")
        }
        if len(processes) != 1:
            return None
        # Monotonic values are comparable only within one running experiment process/boot.
        return max(0, min(m["terminal_record_received"]["monotonic_ns"] for m in measurements)
                   - max(m["dispatch_started"]["monotonic_ns"] for m in measurements)) / 1e9

    def observed_generation(self, group, name, attempts):
        request_ids = {a["request_id"] for a in attempts if a.get("request_id")}
        samples = [sample for sample in self.data.get("generation_samples", {}).get(group, [])
                   if sample.get("batch") == name]
        return generation_overlap(samples, request_ids, self.data["measurements"], {
            a["request_id"]: a.get("upstream_completed_at") for a in attempts if a.get("request_id")
        })

    async def smoke(self):
        await self.verify("smoke")
        first = await self.turn("smoke", "A", "arithmetic", SMOKE)
        if not (first.get("correct_marker") and first.get("addresses_task")):
            raise ValueError("Smoke arithmetic failed; no context or parallel prompt sent")
        second = await self.turn("smoke", "A", "context", SMOKE_CONTEXT, context=True)
        self.data["phases"]["smoke_pass"] = bool(second.get("context_retained"))
        self.save()
        return [first, second]

    async def parallel(self):
        if not self.data["phases"].get("smoke_pass"):
            raise ValueError("Parallel execution requires a passing live smoke/context test")
        results = await self.simultaneous("parallel", "proof", PROMPTS)
        conversations = [a.get("binding", {}).get("bridge_session_id") for a in results]
        overlap = self.overlap(results)
        generation = self.observed_generation("parallel", "proof", results)
        self.data["phases"].update(
            parallel_outputs_pass=all(a.get("correct_marker") and a.get("addresses_task") for a in results)
            and all(conversations) and len(set(conversations)) == 3,
            three_way_in_flight_overlap_seconds=overlap,
            proof_generation_evidence=generation,
            actual_three_way_generation_observed=len(generation["request_ids"]) == 3
            and generation["observed_overlap_seconds"] > 0,
        )
        self.save()
        return results

    async def parallel_two(self):
        failures = self.confirmed_capacity_failure()
        results = await self.simultaneous("two", "proof", {label: PROMPTS[label] for label in "AB"})
        conversations = [a.get("binding", {}).get("bridge_session_id") for a in results]
        self.data["phases"]["two_request_probe"] = {
            "trigger_capacity_requests": failures,
            "outputs_pass": all(a.get("correct_marker") and a.get("addresses_task") for a in results)
            and all(conversations) and len(set(conversations)) == 2,
            "in_flight_overlap_seconds": self.overlap(results),
            "generation_evidence": self.observed_generation("two", "proof", results),
            "classification": "Two-request diagnostic only; does not satisfy three-request LIVE PASS",
        }
        self.save()
        return results

    async def context(self):
        if not self.data["phases"].get("parallel_outputs_pass"):
            raise ValueError("Context test requires three successful distinct live conversations")
        results = await self.simultaneous("parallel", "context", dict.fromkeys("ABC", CONTEXT), context=True)
        self.data["phases"]["context_pass"] = all(
            a.get("context_retained") and a.get("addresses_task") for a in results
        )
        self.data["phases"]["phase2_pass"] = bool(
            self.data["phases"]["context_pass"]
            and self.data["phases"].get("three_way_in_flight_overlap_seconds", 0)
            and self.data["phases"].get("actual_three_way_generation_observed")
        )
        self.save()
        return results

    async def tree(self):
        if not self.data["phases"].get("phase2_pass"):
            raise ValueError("Tree execution requires full Phase 2 with observed concurrent generation")
        await self.verify("tree")
        bridge = self.bridge("tree")
        scheduler = ExperimentScheduler(bridge.store, bridge)
        scheduler.experiment_rounds_per_leaf = self.args.tree_pairs // 2
        scheduler.experiment_nodes = {entry["node_id"] for entry in self.group("tree").values()}
        own_ids = {bridge._request_id(turn["id"]) for turn in bridge.store.query("SELECT id FROM turns")}
        done = asyncio.Event()
        # Request IDs are created lazily by the scheduler; update the set while observing.
        async def watch_tree():
            while not done.is_set():
                own_ids.update(bridge._request_id(row["id"]) for row in bridge.store.query("SELECT id FROM turns"))
                await asyncio.sleep(.2)
        watcher = asyncio.create_task(watch_tree())
        observer = asyncio.create_task(self.observe("tree", done, own_ids, "tree"))
        try:
            completed = bridge.store.one("SELECT COUNT(*) AS n FROM parent_responses")["n"]
            remaining = self.args.tree_pairs - completed
            if remaining > 0:
                await asyncio.wait_for(scheduler.run(max_rounds=remaining), timeout=3600)
        finally:
            done.set()
            await asyncio.gather(watcher, observer)
            await scheduler.aclose()
            for turn in bridge.store.query("SELECT id FROM turns"):
                await self.own_evidence(bridge, turn["id"])
            for label, session in self.group("tree").items():
                session.update(self.binding(bridge, session["id"]))
            summary = {
                "parent_responses": bridge.store.query("SELECT * FROM parent_responses"),
                "rounds": bridge.store.query("SELECT * FROM rounds ORDER BY seq"),
                "events": bridge.store.query("SELECT * FROM events ORDER BY id"),
                "errors": bridge.store.query("SELECT * FROM errors"),
                "sessions": self.group("tree"),
            }
            self.files.atomic_write("tree_summary.json", json.dumps(redact(summary), indent=2) + "\n")
            self.data["phases"]["tree_pairs_completed"] = len(summary["parent_responses"])
            self.save()
        return {"completed_pairs": len(summary["parent_responses"]), "errors": summary["errors"]}


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--browser-instance")
    parser.add_argument("--actual-model-label", choices=("GPT-6 Thinking", "GPT-6"), default="GPT-6 Thinking")
    parser.add_argument("--tree-pairs", type=int, choices=(2, 4), default=2)
    parser.add_argument("command", choices=("init", "prepare", "verify", "smoke", "parallel", "parallel-two", "context", "tree", "status"))
    parser.add_argument("--group", choices=("smoke", "parallel", "two", "tree"), default="smoke")
    args = parser.parse_args()
    harness = Harness(args)
    try:
        if args.command in {"init", "status"}:
            result = harness.data
        elif args.command in {"prepare", "verify"}:
            result = await getattr(harness, args.command)(args.group)
        else:
            result = await getattr(harness, args.command.replace("-", "_"))()
        print(json.dumps(redact(result), indent=2))
    except Exception as exc:
        harness.data.setdefault("command_errors", []).append({
            "command": args.command, "group": args.group, **stamp(),
            "type": type(exc).__name__, "message": str(exc),
        })
        harness.save()
        print(json.dumps(redact({"error": str(exc), "manifest": str(harness.root / "manifest.json")}), indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
