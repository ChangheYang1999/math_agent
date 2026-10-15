#!/usr/bin/env python3
"""Bounded live continuation; old evidence stays immutable and inference stays in Chrome."""

import argparse
import asyncio
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_experiment import (
    BASE, Harness, LiveBridge, ExperimentScheduler, Scheduler, Store,
    COORDINATOR_MODEL, PRO_MODEL, redact, stamp,
)

OLD = BASE / "runs/20261014-live-r2"
EXISTING_TREE = OLD / "projects/tree"
TREE_LABELS = {"Parent": "root", "Leaf-1": "n-e615a92f81c6", "Leaf-2": "n-f9b4c78a7858"}


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def probe_prompt(long=False, *, minimum_characters=16000, marker_kind=None):
    kind = marker_kind or ("LONG" if long else "SHORT")
    begin, end = f"BRIDGE-{kind}-BEGIN-741", f"BRIDGE-{kind}-END-953"
    text = (f"{begin}\nThis is a benign browser transport integrity check. Read the complete input. "
            "Return a concise JSON object only, with keys begin_marker, end_marker, product, and last_reference. "
            "Copy the exact beginning and ending markers, compute 37 * 43, and copy last_reference as a four-character zero-padded string. "
            "The reference material consists of exact arithmetic checks; do not expand every check in your reply.\n")
    n = 0
    while n < 1 or (long and len(text) < minimum_characters):
        n += 1
        text += (f"Reference {n:04d}: For k={n}, k^2-(k-1)^2={n*n}-{(n-1)*(n-1)}={2*n-1}. "
                 "This follows by expanding both squares and is one instance of the telescoping identity.\n")
    text += f"Last reference is {n:04d}. Copy both exact markers and return product 37 * 43.\n{end}"
    return text, {"begin_marker": begin, "end_marker": end, "product": 1591, "last_reference": f"{n:04d}"}


class ProductionScheduler(ExperimentScheduler):
    async def _session(self, node_id, model):
        if node_id not in self.experiment_nodes:
            raise ValueError("Disposable production-role topology is frozen")
        return await Scheduler._session(self, node_id, model)


class Continuation(Harness):
    def bridge(self, group):
        if group == "tree" and group not in self.bridges:
            self.bridges[group] = LiveBridge(Store(EXISTING_TREE), self, group)
        return super().bridge(group)

    def snapshot(self):
        baseline = json.loads((OLD / "manifest.json").read_text())
        if not baseline["phases"].get("phase2_pass"):
            raise ValueError("Saved live concurrency baseline did not pass")
        target = self.root / "snapshots"
        target.mkdir(exist_ok=True)
        if not (target / "baseline.json").exists():
            paths = [OLD / "manifest.json", BASE / "RESULTS.md", BASE / "tree_audit.json",
                     *sorted((OLD / "evidence").glob("*.json"))]
            hashes = {str(p.relative_to(BASE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
            (target / "baseline.json").write_text(json.dumps({**stamp(), "sha256": hashes}, indent=2) + "\n")
            with sqlite3.connect(EXISTING_TREE / "tree.db") as source, sqlite3.connect(target / "tree_before.db") as destination:
                source.backup(destination)
        self.data["baseline"] = {"run": baseline["run_id"], "snapshot": "snapshots/baseline.json"}
        self.data["phases"]["phase2_pass"] = True  # Referenced saved live baseline, not a new concurrency claim.
        self.save()

    def long19k_prerequisite(self):
        if not self.data["phases"].get("short_pass"):
            raise ValueError("The separate 19k probe requires the live short baseline")
        store = self.bridge("long").store
        original = store.one("SELECT * FROM turns WHERE id='direct-long-16000'")
        if not original:
            raise ValueError("The original 16k request must exist and reach an authoritative terminal state")
        old_session = store.one("SELECT * FROM sessions WHERE id=?", (original["session_id"],))
        if original["status"] == "COMPLETED" and original["raw_response"] is not None:
            return old_session
        isolated = self.data.get("isolated_sent_diagnostic") or {}
        if (isolated.get("request_id") != original["bridge_request_id"]
                or isolated.get("terminal_status") != "interrupted"
                or isolated.get("prompt_sha256") != sha(original["prompt"])):
            raise ValueError("An interrupted 16k request requires explicit exact isolated_sent_diagnostic evidence; no replay permitted")
        diagnostic = json.loads(self.files.resolve(isolated["actual_ui_reply_evidence"]).read_text())
        interruption = json.loads(self.files.resolve(isolated["authoritative_terminal_evidence"]).read_text())
        terminal = (interruption.get("result") or {}).get("turn") or {}
        reply = (diagnostic.get("diagnostic_reply") or {}).get("result") or {}
        observed = diagnostic.get("ui_dom_read") or {}
        if (terminal.get("id") != original["bridge_request_id"] or terminal.get("status") != "interrupted"
                or terminal.get("output") is not None or (terminal.get("input") or {}).get("message") != original["prompt"]
                or interruption.get("proven_not_executed") is not False or interruption.get("no_retry_permitted") is not True
                or diagnostic.get("request_id") != original["bridge_request_id"]
                or observed.get("sha256") != sha(original["prompt"]) or observed.get("characters") != len(original["prompt"])
                or not reply.get("answer") or reply.get("sourceClientId") != terminal["input"].get("sourceClientId")
                or (reply.get("session") or {}).get("id") != terminal["input"].get("sessionId")):
            raise ValueError("Saved sent-diagnostic isolation is incomplete or mismatched; no new probe permitted")
        return old_session

    def final_probe_prerequisite(self):
        original_session = self.long19k_prerequisite()
        row = self.bridge("long19k").store.one("SELECT * FROM turns WHERE id='direct-long19k'")
        evidence = json.loads((self.root / "long19_interruption.json").read_text())
        terminal = evidence["result"]["turn"]
        if (not row or row["status"] != "ERROR" or row["raw_response"] is not None
                or terminal["id"] != row["bridge_request_id"] or terminal["status"] != "interrupted"
                or terminal["input"]["message"] != row["prompt"]
                or evidence.get("no_retry_permitted") is not True):
            raise ValueError("Final independent probe requires the exact 19k diagnostic safely isolated")
        self.data["final_probe_limit"] = "One distinct LONG20K message; never replay either interrupted input"
        return original_session

    async def prepare_probe(self, extended=False, final=False):
        if extended:
            self.long19k_prerequisite()
        if final:
            self.final_probe_prerequisite()
        group, node = ("long20k", "long20k-probe") if final else ("long19k", "long19k-probe") if extended else ("long", "long-probe")
        bridge = self.bridge(group)
        session = await bridge.create_session(node, COORDINATOR_MODEL, self.args.run + ":" + node)
        self.data["sessions"][group] = {"Probe": self.binding(bridge, session.id)}
        self.save()
        return await self.verify(group)

    async def probe(self, long=False, math=False, minimum_characters=None, final=False, math_final=False):
        extended = minimum_characters is not None
        if long and not self.data["phases"].get("short_pass"):
            raise ValueError("Direct long input requires the live short baseline first")
        if math and not any(self.data["phases"].get(k) for k in ("long_pass", "long19k_pass", "long20k_pass")):
            raise ValueError("Math/code check follows the direct live long-input test")
        group = "long20k" if final or (math and self.data["phases"].get("long20k_pass")) else "long19k" if extended or (math and self.data["phases"].get("long19k_pass")) else "long"
        old_session = self.long19k_prerequisite() if extended else None
        bridge = self.bridge(group)
        session = bridge.get_session(self.group(group)["Probe"]["id"])
        prompt, expected = probe_prompt(long)
        key = "direct-long-16000" if long else "direct-short"
        if extended:
            if minimum_characters <= 19000:
                raise ValueError("The independent 19k payload must be larger than 19,000 characters")
            saved_minimum = self.data.setdefault(group + "_minimum_characters", minimum_characters)
            if saved_minimum != minimum_characters:
                raise ValueError("The existing 19k probe minimum is immutable; no changed-payload resend")
            binding = self.binding(bridge, session.id)
            if (session.id == old_session["id"] or binding["bridge_client_id"] == old_session["bridge_client_id"]
                    or binding["bridge_session_id"] and binding["bridge_session_id"] == old_session["bridge_session_id"]):
                raise ValueError("The 19k diagnostic requires its own separate conversation and tab")
            if final:
                self.final_probe_prerequisite()
                previous = self.group("long19k")["Probe"]
                if session.id == previous["id"] or binding["bridge_client_id"] == previous["bridge_client_id"]:
                    raise ValueError("The final diagnostic must use a separate new conversation")
            prompt, expected = probe_prompt(True, minimum_characters=minimum_characters, marker_kind="LONG20K" if final else "LONG19K")
            key = "direct-long20k" if final else "direct-long19k"
        if math:
            key = "direct-math-code19k" if group == "long19k" else "direct-math-code"
            prompt = ("Reply concisely with marker MATH-CODE-BEGIN-327, then typeset the exact TeX formula "
                      "\\sqrt{2}+\\frac{1}{2}+x_i^2 as display math. Then include a fenced python block "
                      "containing exactly these two lines:\nvalue = \"sqrt(2)\"\nprint(value)\n"
                      "End with MATH-CODE-END-684. Do not explain or execute the code.")
            expected = {"markers": ["MATH-CODE-BEGIN-327", "MATH-CODE-END-684"],
                        "math": ["\\sqrt{2}", "\\frac{1}{2}", "x_i"],
                        "code": '```python\nvalue = "sqrt(2)"\nprint(value)\n```'}
            if math_final:
                key = "direct-math-code-final"
                prompt = prompt.replace("BEGIN-327", "BEGIN-428").replace("END-684", "END-795")
                expected["markers"] = ["MATH-CODE-BEGIN-428", "MATH-CODE-END-795"]
        if self.args.probe_epoch:
            key += f"-e{self.args.probe_epoch}"
        record = self.data["attempts"].setdefault(key, {
            "phase": group, "label": "Probe", "started": stamp(), "prompt": prompt,
            "prompt_characters": len(prompt), "prompt_utf8_bytes": len(prompt.encode()),
            "prompt_sha256": sha(prompt), "expected": expected,
        })
        if record["prompt_sha256"] != sha(prompt):
            raise ValueError("Existing approved prompt differs; no replay permitted")
        self.save()
        try:
            await bridge.send_message(session, prompt, key)
            answer = await bridge.await_response(session, key)
            if math:
                matched = all(v in answer for v in expected["markers"] + expected["math"] + [expected["code"]])
            else:
                parsed = json.loads(answer)
                matched = all(str(parsed.get(k)) == str(v) for k, v in expected.items())
            record.update(answer=answer, exact_reply_fields=matched, terminal_status="COMPLETED")
            record.pop("error", None)
        except Exception as exc:
            record.update(error=str(exc), terminal_status="ERROR_OR_UNCERTAIN")
            raise
        finally:
            record["finished"] = stamp()
            try:
                evidence = await self.own_evidence(bridge, key)
            except Exception as exc:
                record["evidence_error"] = str(exc)
                evidence = {}
            record["request_id"] = evidence.get("request_id")
            record["upstream_status"] = (evidence.get("turn") or {}).get("status")
            confirmations = [e for e in evidence.get("events", [])
                             if e.get("type") == "diagnostic.chat.prompt.submit.confirmed"]
            record["send_confirmation"] = confirmations
            record["full_submitted_text_verified"] = any(
                (p := e.get("data", {}).get("payload", {})).get("fullPromptTextMatch") is True
                and p.get("expectedSha256") == record["prompt_sha256"]
                and p.get("observedSha256") == record["prompt_sha256"]
                and p.get("observedCharacters") == record["prompt_characters"]
                for e in confirmations)
            self.data["sessions"][group]["Probe"].update(self.binding(bridge, session.id))
            record["binding"] = self.binding(bridge, session.id)
            self.data["phases"]["math_code_final_pass" if math_final else "long20k_pass" if final else "long19k_pass" if extended else "math_code_pass" if math else "long_pass" if long else "short_pass"] = bool(
                record.get("exact_reply_fields") and record.get("full_submitted_text_verified")
                and record.get("upstream_status") == "completed")
            self.save()
        return {k: v for k, v in record.items() if k not in {"prompt", "answer", "send_confirmation"}}

    async def bind_tree(self):
        bridge = self.bridge("tree")
        clients = (await bridge._json("GET", "/browser/clients"))["clients"]
        audit = []
        for label, node in TREE_LABELS.items():
            row = bridge.store.one("SELECT * FROM sessions WHERE node_id=? AND active=1", (node,))
            matches = [c for c in clients if c.get("url") == row["url"]]
            if len(matches) != 1:
                raise ValueError(f"Expected exactly one connected saved {label} conversation; no tab opened")
            if bridge.store.one("SELECT id FROM turns WHERE session_id=? AND raw_response IS NULL AND status!='FAILED_NOT_SENT'", (row["id"],)):
                raise ValueError("Resolve the exact stopped turn with positive evidence before rebinding")
            audit.append({"session_id": row["id"], "conversation_id": row["bridge_session_id"],
                          "previous_client": row["bridge_client_id"], "client": matches[0]["id"]})
        with bridge.store.transaction() as c:
            for row in audit:
                c.execute("UPDATE sessions SET bridge_client_id=? WHERE id=?", (row["client"], row["session_id"]))
            bridge.store.event("experiment_persistent_conversations_rebound", {**stamp(), "bindings": audit}, c)
        self.data["sessions"]["tree"] = {
            label: self.binding(bridge, bridge.store.one("SELECT id FROM sessions WHERE node_id=? AND active=1", (node,))["id"])
            for label, node in TREE_LABELS.items()}
        self.files.atomic_write("tree_rebinding.json", json.dumps({**stamp(), "bindings": audit}, indent=2) + "\n")
        self.save()
        return await self.verify("tree")


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["snapshot", "prepare", "prepare19k", "prepare20k", "short", "long", "long19k", "long20k", "math", "math-final", "bind-tree", "tree"])
    parser.add_argument("--run", default="20261015-long-prompt")
    parser.add_argument("--probe-epoch", type=int, default=0)
    parser.add_argument("--minimum-characters", type=int, default=19500)
    args = parser.parse_args()
    args.actual_model_label, args.browser_instance, args.tree_pairs = "GPT-6", "Existing Chrome profile yang; persistent browser instance", 4
    h = Continuation(args)
    h.snapshot()
    if args.command == "snapshot":
        result = h.data["baseline"]
    elif args.command in {"prepare", "prepare19k", "prepare20k"}:
        result = await h.prepare_probe(args.command != "prepare", args.command == "prepare20k")
    elif args.command in {"long19k", "long20k"}:
        result = await h.probe(True, minimum_characters=max(20000, args.minimum_characters) if args.command == "long20k" else args.minimum_characters, final=args.command == "long20k")
    elif args.command in {"short", "long", "math", "math-final"}:
        result = await h.probe(args.command == "long", args.command in {"math", "math-final"}, math_final=args.command == "math-final")
    elif args.command == "bind-tree":
        result = await h.bind_tree()
    else:
        if not any(h.data["phases"].get(k) for k in ("long_pass", "long19k_pass", "long20k_pass")):
            raise ValueError("Four-pair continuation requires direct live long-input success first")
        result = await h.tree()
    print(json.dumps(redact(result), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
