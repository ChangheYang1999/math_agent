"""Asynchronous per-leaf protocol. P0 checkpoints precede optional tree/report work."""

from __future__ import annotations

import asyncio
import fcntl
import json
import re
from contextlib import nullcontext
from importlib import resources
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from .recovery import unresolved_turns
from .schemas import (
    PARENT_MODEL,
    PRO_MODEL,
    BootstrapResponse,
    CoordinationResponse,
    LeafRoundReport,
    ParentDiscussionResponse,
    ParentRoundResponse,
    ReportUpdate,
    TranslationResponse,
    UserDisplayTranslation,
    require_english,
)
from .store import Store, digest, encode
from .transport import (
    ManualRelayTransport,
    RelayPending,
    ScriptedTransport,
    Session,
    TransportError,
)


def render_prompt(name, context, schema):
    local = Path(__file__).resolve().parents[2] / "prompts" / f"{name}.md"
    text = (
        local.read_text(encoding="utf-8")
        if local.exists()
        else resources.files("math_research_agent").joinpath("prompts", f"{name}.md").read_text()
    )
    output_schema = schema.model_json_schema()
    schema_text = encode(output_schema)
    if name == "parent_response":
        from .parent_prompt import compact_schema

        output_schema = compact_schema(output_schema)
        schema_text = json.dumps(
            output_schema, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        )
    return text + "\nCONTEXT_JSON\n" + encode(context) + "\nOUTPUT_SCHEMA_JSON\n" + schema_text


class ContractFailure(ValueError):
    def __init__(self, operation, detail):
        self.operation = operation
        super().__init__(f"Format repair exhausted for {operation}: {detail}")


def preserve_math(original, translated):
    """Keep explicit math spans verbatim at the human translation boundary."""
    pattern = r"\$\$[\s\S]*?\$\$|\$[^$\n]+\$|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]|\\[A-Za-z]+(?:\{[^{}]*\})*|(?<!\w)[A-Za-z]\w*\s*=\s*[A-Za-z0-9_+*/^().-]+"
    if any(match.group() not in translated for match in re.finditer(pattern, original)):
        raise ValueError(
            "Boundary translation must preserve all original formulas and LaTeX verbatim"
        )


class Scheduler:
    def __init__(self, store: Store, transport=None):
        self.store = store
        if transport is None:
            if store.config.transport == "bridge":
                from .bridge_transport import BridgeTransport

                transport = BridgeTransport(store)
            else:
                transport = (
                    ScriptedTransport(store)
                    if store.config.transport == "fake"
                    else ManualRelayTransport(store)
                )
        self.transport = transport
        self._tasks = {}
        self._locks = {}
        self._lockfile = None
        self._max_pairs = None
        self._baseline = 0
        self._closed = False

    def _acquire(self):
        if self._lockfile is None:
            f = (self.store.root / ".runner.lock").open("a+")
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                f.close()
                raise ValueError(
                    "A scheduler is already running for this project. Use its dashboard or stop it first."
                ) from None
            self._lockfile = f

    async def aclose(self):
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        if self._lockfile:
            fcntl.flock(self._lockfile, fcntl.LOCK_UN)
            self._lockfile.close()
            self._lockfile = None
        self._closed = True
        if hasattr(self.transport, "aclose"):
            await self.transport.aclose()

    async def _session(self, node_id, model):
        current = self.store.one(
            "SELECT * FROM sessions WHERE node_id=? AND model=? AND active=1 ORDER BY created_at DESC LIMIT 1",
            (node_id, model),
        )
        session = (
            Session(current["id"], node_id, model, current["url"])
            if current and self.store.config.transport != "bridge"
            else await self.transport.create_session(node_id, model, f"{node_id}:{model}")
        )
        if session.model != model:
            raise TransportError(f"Required ChatGPT model unavailable: {model}")
        if node_id != "__user_translation__":
            self.store.execute(
                "UPDATE nodes SET conversation_id=? WHERE id=?", (session.id, node_id)
            )
        return session

    async def _request(
        self,
        actor_id,
        model,
        name,
        context,
        output_type,
        key,
        *,
        exact_prompt=None,
        expected=None,
        validate=None,
    ):
        session = await self._session(actor_id, model)
        lock = self._locks.setdefault(session.id, asyncio.Lock())
        async with lock:
            if name == "parent_response":
                from .parent_prompt import parent_context

                context = parent_context(self.store, context, session)
            epoch = self.store.setting("retry:" + key, 0)
            original = exact_prompt or render_prompt(name, context, output_type)
            if context.get("kind") not in ("translation", "display_translation"):
                require_english(original)
            error = None
            for attempt in range(self.store.config.format_retries + 1):
                turn_id = f"{key}:e{epoch}:a{attempt}"
                existing = self.store.one("SELECT * FROM turns WHERE id=?", (turn_id,))
                if existing:
                    prompt = existing["prompt"]
                elif attempt:
                    prompt = (
                        original
                        + "\nFORMAT_REPAIR: Your last reply failed the required contract: "
                        + str(error)
                        + "\nReturn a corrected complete JSON object only. Keep the exact IDs, include all required fields, use English, and preserve the research evidence. This is repair of the same round, not another research round."
                    )
                else:
                    prompt = original
                if context.get("kind") not in ("translation", "display_translation"):
                    require_english(prompt)
                # A manual/uncertain outstanding turn owns this conversation until resolved.
                pending = next(iter(unresolved_turns(self.store, session.id, turn_id)), None)
                if pending:
                    raise RelayPending(pending["id"])
                if not existing:
                    self.store.execute(
                        "INSERT INTO turns(id,session_id,prompt,status) VALUES(?,?,?,'PENDING')",
                        (turn_id, session.id, prompt),
                    )
                if not existing or (
                    existing["raw_response"] is None and existing["status"] in ("PENDING", "QUEUED")
                ):
                    # Reserve once before crossing the transport boundary. An uncertain delivery
                    # is recovered by awaiting this turn, never by sending a second request.
                    self.store.execute("UPDATE turns SET status='REQUESTED' WHERE id=?", (turn_id,))
                    await self.transport.send_message(session, prompt, turn_id)
                raw = await self.transport.await_response(session, turn_id)
                # The transport must retain the raw text even if validation fails.
                self.store.execute(
                    "UPDATE turns SET raw_response=COALESCE(raw_response,?) WHERE id=?",
                    (raw, turn_id),
                )
                try:
                    text = raw.strip()
                    if text.startswith("```") and text.endswith("```"):
                        text = "\n".join(text.splitlines()[1:-1])
                    output = output_type.model_validate_json(text)
                    for field, value in (expected or {}).items():
                        if getattr(output, field) != value:
                            raise ValueError(f"{field} must be exactly {value}")
                    if validate is not None:
                        validate(output)
                    self.store.execute(
                        "UPDATE turns SET status='COMPLETED',error=NULL WHERE id=?", (turn_id,)
                    )
                    return output
                except (ValueError, ValidationError) as exc:
                    # ValidationError.__str__ includes the rejected input, which may contain Chinese.
                    error = (
                        encode(
                            exc.errors(
                                include_input=False, include_url=False, include_context=False
                            )
                        )
                        if isinstance(exc, ValidationError)
                        else str(exc)
                    )
                    try:
                        require_english(error)
                    except ValueError:
                        error = "The reply violated the English-only structured output contract."
                    self.store.execute(
                        "UPDATE turns SET status='INVALID',error=? WHERE id=?", (error, turn_id)
                    )
            raise ContractFailure(key, error)

    def _launch(self, key, coroutine, affected_node, *, operation=None, optional=False):
        if key in self._tasks:
            coroutine.close()
            return False

        async def guarded():
            try:
                await coroutine
            except RelayPending:
                pass  # Waiting is durable and visible; never fabricate a reply.
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                message = str(exc) or type(exc).__name__
                failed_operation = getattr(exc, "operation", operation or key)
                self.store.execute(
                    "INSERT INTO errors(node_id,operation,message) VALUES(?,?,?)",
                    (affected_node, failed_operation, message),
                )
                self.store.event(
                    "recoverable_error",
                    {"node_id": affected_node, "operation": failed_operation, "message": message},
                )
                if optional:
                    self.store.set_setting("optional_error:" + key, True)
                    if key.startswith("discussion:"):
                        self.store.execute(
                            "UPDATE review_messages SET status='ERROR' WHERE id=?",
                            (key.removeprefix("discussion:"),),
                        )
                    self.store.execute(
                        "UPDATE optional_jobs SET status='ERROR',error=? WHERE id=?", (message, key)
                    )
                else:
                    self.store.execute(
                        "UPDATE nodes SET runtime_state='ERROR' WHERE id=?", (affected_node,)
                    )

        self._tasks[key] = asyncio.create_task(guarded())
        return True

    async def _bootstrap(self):
        node = self.store.node("root")

        def validate(out):
            if len(out.children) > self.store.config.target_active_leaves:
                raise ValueError("Bootstrap exceeds leaf capacity; propose fewer concrete tasks")

        out = await self._request(
            "root",
            PARENT_MODEL,
            "parent_bootstrap",
            {
                "kind": "bootstrap",
                "node_id": "root",
                "goal": node["goal"],
                "research_state": node["research_state"],
                "leaf_capacity": self.store.config.max_active_leaves,
                "capacity_is_maximum": True,
            },
            BootstrapResponse,
            "bootstrap:root",
            validate=validate,
        )
        if not self.store.children("root"):
            self.store.split("root", out.children, actor_id="root")
            self.store.execute(
                "UPDATE nodes SET research_state=? WHERE id=?", (out.research_state, "root")
            )
            self.store.set_setting("coordinator_ready:root", True)

    async def _restore_internal(self, node_id):
        node = self.store.node(node_id)
        children = self.store.children(node_id)
        tasks = []
        for child in children:
            r = self.store.one(
                "SELECT * FROM rounds WHERE node_id=? AND stage IN ('PROMPT_READY','PROMPT_APPROVAL') ORDER BY seq DESC LIMIT 1",
                (child["id"],),
            )
            if not r:
                raise ValueError("Promoted coordinator requires undispatched concrete child tasks")
            tasks.append(
                {
                    "goal": child["goal"],
                    "relative_weight": child["relative_weight"],
                    "initial_prompt": r["task"],
                }
            )

        def validate(out):
            if len(out.children) != len(children) or any(
                t.goal != c["goal"] or abs(t.relative_weight - c["relative_weight"]) > 1e-8
                for t, c in zip(out.children, children, strict=False)
            ):
                raise ValueError(
                    "Bootstrap must preserve existing child goals and weights; propose structural changes afterward"
                )

        out = await self._request(
            node_id,
            PARENT_MODEL,
            "parent_bootstrap",
            {
                "kind": "bootstrap",
                "node_id": node_id,
                "goal": node["goal"],
                "research_state": node["research_state"],
                "existing_children": tasks,
                "leaf_capacity": self.store.allocation()[node_id]["leaf_capacity"],
                "capacity_is_maximum": True,
            },
            BootstrapResponse,
            "restore:" + node_id,
            validate=validate,
        )
        for child, task in zip(children, out.children, strict=True):
            r = self.store.one(
                "SELECT * FROM rounds WHERE node_id=? AND stage IN ('PROMPT_READY','PROMPT_APPROVAL') ORDER BY seq DESC LIMIT 1",
                (child["id"],),
            )
            if r["task"] != task.initial_prompt:
                self.store.revise_prompt(r["id"], task.initial_prompt)
        self.store.execute(
            "UPDATE nodes SET research_state=? WHERE id=?", (out.research_state, node_id)
        )
        self.store.set_setting("coordinator_ready:" + node_id, True)
        self.store.event(
            "coordinator_restored", {"node_id": node_id, "children": [c["id"] for c in children]}
        )

    def _ancestors_ready(self, node_id):
        node = self.store.node(node_id)
        while node["parent_id"]:
            node = self.store.node(node["parent_id"])
            if not self.store.setting("coordinator_ready:" + node["id"], True):
                return False
        return True

    def _gates(self):
        with self.store.transaction() as c:
            rows = c.execute(
                "SELECT * FROM rounds WHERE stage IN ('PROMPT_APPROVAL','REPORT_APPROVAL')"
            ).fetchall()
            for r in rows:
                kind = "prompt" if r["stage"] == "PROMPT_APPROVAL" else "report"
                version = r["prompt_version"] if kind == "prompt" else 1
                a = c.execute(
                    "SELECT * FROM approvals WHERE round_id=? AND artifact_type=? AND version=?",
                    (r["id"], kind, version),
                ).fetchone()
                if a and a["status"] in ("APPROVED", "AUTO_APPROVED"):
                    payload = r["prompt"] if kind == "prompt" else r["report"]
                    if digest(payload) != a["content_hash"]:
                        raise ValueError(
                            "Approved artifact has changed; a new version must be reviewed"
                        )
                    c.execute(
                        "UPDATE rounds SET stage=?,report_accepted=CASE WHEN ? THEN 1 ELSE report_accepted END WHERE id=?",
                        (
                            "PROMPT_READY" if kind == "prompt" else "AWAITING_PARENT_RESPONSE",
                            kind == "report",
                            r["id"],
                        ),
                    )
                    self.store.event(
                        "gate_crossed", {"round_id": r["id"], "artifact_type": kind}, c
                    )

    async def _leaf(self, round_id):
        r = self.store.one("SELECT * FROM rounds WHERE id=?", (round_id,))
        if r["stage"] == "PROMPT_APPROVAL":
            return  # Review may have been enabled after this task was queued locally.
        n = self.store.node(r["node_id"])
        if r["previous_round_id"]:
            prior = self.store.one("SELECT * FROM rounds WHERE id=?", (r["previous_round_id"],))
            response = self.store.one(
                "SELECT * FROM parent_responses WHERE round_id=? AND next_round_id=?",
                (prior["id"], r["id"]),
            )
            if not prior["report"] or not response:
                raise ValueError(
                    "Leaf cannot continue without its report and linked parent response"
                )
            if not prior["report_accepted"] and r["kind"] != "correction":
                raise ValueError("An unapproved report requires a linked correction attempt")
        # Gate crossing is recorded before sending. Turning ON later does not retroactively stop this turn.
        if r["stage"] == "PROMPT_READY":
            a = self.store.one(
                "SELECT * FROM approvals WHERE round_id=? AND artifact_type='prompt' AND version=?",
                (r["id"], r["prompt_version"]),
            )
            if (
                not a
                or a["status"] not in ("APPROVED", "AUTO_APPROVED")
                or a["content_hash"] != digest(r["prompt"])
            ):
                raise ValueError("Exact prompt requires approval before dispatch")
            self.store.execute(
                "UPDATE rounds SET stage='SOLVING',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (r["id"],),
            )
            self.store.event("leaf_dispatched", {"node_id": n["id"], "round_id": r["id"]})
        key = f"leaf:{r['id']}"
        out = await self._request(
            n["id"],
            PRO_MODEL,
            "leaf_round",
            {"kind": "leaf"},
            LeafRoundReport,
            key,
            exact_prompt=r["prompt"],
            expected={"node_id": n["id"], "round_id": r["id"]},
        )
        self._commit_leaf_report(round_id, out)

    def _commit_leaf_report(self, round_id, out, *, connection=None):
        """Persist one validated report and its existing human-review/P0 gate."""
        with self.store.transaction() if connection is None else nullcontext(connection) as c:
            r = c.execute("SELECT * FROM rounds WHERE id=?", (round_id,)).fetchone()
            n = c.execute("SELECT * FROM nodes WHERE id=?", (r["node_id"],)).fetchone()
            if out.node_id != n["id"] or out.round_id != round_id:
                raise ValueError("Leaf report IDs do not match the exact round")
            if r["report"]:
                if r["report"] != encode(out):
                    raise ValueError("The round already has a different Leaf report")
                return
            payload = encode(out)
            review = self.store.artifact(c, n["id"], r["id"], "report", payload)
            stage = "REPORT_APPROVAL" if review else "AWAITING_PARENT_RESPONSE"
            c.execute(
                "UPDATE rounds SET report=?,stage=?,report_accepted=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (payload, stage, int(not review), r["id"]),
            )
            try:
                prior_state = json.loads(n["research_state"])
                if not isinstance(prior_state, dict):
                    prior_state = {}
            except (ValueError, TypeError):
                prior_state = {}
            findings = list(dict.fromkeys([*prior_state.get("findings", []), *out.findings]))
            important_rounds = prior_state.get("important_rounds", [])
            if out.important_update and r["id"] not in important_rounds:
                important_rounds = [*important_rounds, r["id"]]
            state = encode(
                {
                    "summary": out.summary,
                    "findings": findings,
                    "obstacles": out.obstacles,
                    "evidence": out.evidence,
                    "last_round_id": r["id"],
                    "important_rounds": important_rounds,
                }
            )
            c.execute(
                "UPDATE nodes SET research_state=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (state, n["id"]),
            )
            self.store.event("report_stored", {"round_id": r["id"], "parent_id": n["parent_id"]}, c)

    def _queue_optional(self, actor_id, response, source_key, c):
        for field, priority, kind in [
            ("proposed_tree_actions", 1, "tree"),
            ("proposed_messages", 1, "message"),
            ("proposed_report_updates", 2, "section"),
        ]:
            for i, item in enumerate(getattr(response, field, [])):
                c.execute(
                    "INSERT OR IGNORE INTO optional_jobs(id,priority,kind,actor_id,payload) VALUES(?,?,?,?,?)",
                    (f"{source_key}:{kind}:{i}", priority, kind, actor_id, encode(item)),
                )

    def _commit_parent(self, round_id, parent_id, out, *, feedback_id=None):
        with self.store.transaction() as c:
            r = c.execute("SELECT * FROM rounds WHERE id=?", (round_id,)).fetchone()
            existing = c.execute(
                "SELECT * FROM parent_responses WHERE round_id=?", (round_id,)
            ).fetchone()
            if existing:
                return existing["next_round_id"]
            if not r["report"]:
                raise ValueError("Parent response requires a stored leaf report")
            c.execute(
                "UPDATE rounds SET stage='RESPONDED',updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (round_id,),
            )
            # This transaction saves the mandatory next prompt before optional jobs exist.
            next_id = self.store.create_round(
                r["node_id"],
                out.next_prompt,
                round_id,
                "correction" if feedback_id else "research",
                c,
            )
            c.execute(
                "INSERT INTO parent_responses(round_id,parent_id,payload,next_round_id,source) VALUES(?,?,?,?,?)",
                (
                    round_id,
                    parent_id,
                    encode(out),
                    next_id,
                    "feedback" if feedback_id else "report",
                ),
            )
            if feedback_id:
                c.execute(
                    "UPDATE feedback SET status='COMPLETED',response=? WHERE id=?",
                    (encode(out), feedback_id),
                )
            self.store.event(
                "parent_response_stored",
                {"round_id": round_id, "next_round_id": next_id, "parent_id": parent_id},
                c,
            )
            self._queue_optional(parent_id, out, "parent:" + round_id, c)
            # Significant leaf evidence belongs only to the leaf's own section.
            report = LeafRoundReport.model_validate_json(r["report"])
            if report.important_update and r["report_accepted"]:
                update = ReportUpdate(
                    node_id=r["node_id"],
                    body=report.summary + "\n\n" + report.evidence,
                    claim_status="MODEL_PROPOSED",
                    significant=True,
                    evidence_reference=round_id,
                )
                c.execute(
                    "INSERT OR IGNORE INTO optional_jobs(id,priority,kind,actor_id,payload) VALUES(?,?,?,?,?)",
                    ("finding:" + round_id, 2, "section", r["node_id"], encode(update)),
                )
            parent = c.execute(
                "SELECT research_state FROM nodes WHERE id=?", (parent_id,)
            ).fetchone()
            try:
                parent_state = json.loads(parent["research_state"])
                if not isinstance(parent_state, dict):
                    parent_state = {"summary": parent["research_state"]}
            except ValueError:
                parent_state = {"summary": parent["research_state"]}
            parent_state.setdefault("child_assessments", {})[r["node_id"]] = out.assessment
            parent_state["last_child_round"] = round_id
            important = parent_state.setdefault("important_rounds", [])
            if report.important_update and r["report_accepted"] and round_id not in important:
                important.append(round_id)
            # Compact per-child summaries survive rollover; complete evidence remains in linked rounds.
            c.execute(
                "UPDATE nodes SET research_state=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (
                    encode(parent_state),
                    parent_id,
                ),
            )
            return next_id

    async def _parent(self, round_id):
        r = self.store.one("SELECT * FROM rounds WHERE id=?", (round_id,))
        n = self.store.node(r["node_id"])
        parent = self.store.node(n["parent_id"])
        all_nodes = self.store.allocation()
        allocation = all_nodes[parent["id"]]
        inbound = self.store.query(
            "SELECT * FROM messages WHERE recipient_node_id=? AND status='PENDING' ORDER BY created_at,id",
            (parent["id"],),
        )
        out = await self._request(
            parent["id"],
            PARENT_MODEL,
            "parent_response",
            {
                "kind": "parent",
                "node_id": parent["id"],
                "child_node_id": n["id"],
                "round_id": r["id"],
                "goal": parent["goal"],
                "child_goal": n["goal"],
                "research_state": parent["research_state"],
                "children": [
                    {
                        field: child[field]
                        for field in (
                            "id",
                            "goal",
                            "status",
                            "relative_weight",
                            "leaf_capacity",
                            "active_leaves",
                            "unused_capacity",
                        )
                    }
                    for child in all_nodes.values()
                    if child["parent_id"] == parent["id"]
                ],
                "report": json.loads(r["report"]),
                "inbound_internal_messages": inbound,
                "allocation": {
                    "leaf_capacity": allocation["leaf_capacity"],
                    "active_leaves": allocation["active_leaves"],
                    "unused_capacity": allocation["unused_capacity"],
                    "previous_capacity": self.store.setting("allocation_notified:" + parent["id"]),
                },
            },
            ParentRoundResponse,
            "parent:" + r["id"],
            expected={"child_node_id": n["id"], "responding_to_round_id": r["id"]},
        )
        self._commit_parent(r["id"], parent["id"], out)
        for msg in inbound:
            self.store.execute("UPDATE messages SET status='DELIVERED' WHERE id=?", (msg["id"],))
        self.store.set_setting("allocation_notified:" + parent["id"], allocation["leaf_capacity"])

    def _pending_control(self, node_id):
        ancestors = {node_id}
        node = self.store.node(node_id)
        while node["parent_id"]:
            ancestors.add(node["parent_id"])
            node = self.store.node(node["parent_id"])
        for job in self.store.query(
            "SELECT payload FROM optional_jobs WHERE kind='tree' AND status='PENDING'"
        ):
            action = json.loads(job["payload"])
            if (
                action["type"] in ("pause", "complete", "abandon", "split")
                and action["node_id"] in ancestors
            ):
                return True
        return False

    def ask_parent(self, approval_id, content_hash, comment):
        if not isinstance(comment, str) or not comment.strip():
            raise ValueError("Provide a question for this artifact's parent")
        message_id = "q-" + uuid4().hex
        with self.store.transaction() as c:
            approval = c.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
            if not approval or approval["status"] != "PENDING":
                raise ValueError("Questions must refer to a pending approval version")
            if approval["content_hash"] != content_hash:
                raise ValueError("Content changed. Ask about the exact current version.")
            c.execute(
                "INSERT INTO review_messages(id,approval_id,node_id,round_id,content_hash,version,original_message) VALUES(?,?,?,?,?,?,?)",
                (
                    message_id,
                    approval_id,
                    approval["node_id"],
                    approval["round_id"],
                    content_hash,
                    approval["version"],
                    comment.strip(),
                ),
            )
            self.store.event(
                "parent_question_queued",
                {
                    "message_id": message_id,
                    "approval_id": approval_id,
                    "version": approval["version"],
                },
                c,
            )
        return message_id

    async def _translate_user(self, text, key):
        try:
            return require_english(text)
        except ValueError:
            translated = await self._request(
                "__user_translation__",
                PARENT_MODEL,
                "user_translation",
                {
                    "kind": "translation",
                    "source_text": text,
                    "instruction": "Translate human feedback into English and preserve all mathematical notation exactly.",
                },
                TranslationResponse,
                "translate:" + key,
                validate=lambda output: preserve_math(text, output.english_text),
            )
            return translated.english_text

    async def _discussion(self, message_id):
        message = self.store.one("SELECT * FROM review_messages WHERE id=?", (message_id,))
        approval = self.store.one("SELECT * FROM approvals WHERE id=?", (message["approval_id"],))
        leaf = self.store.node(message["node_id"])
        parent = self.store.node(leaf["parent_id"])
        english = message["english_message"]
        if english is None:
            english = await self._translate_user(message["original_message"], message_id)
            self.store.execute(
                "UPDATE review_messages SET english_message=? WHERE id=?", (english, message_id)
            )
        reply = message["reply"]
        if reply is None:
            history = self.store.query(
                "SELECT english_message,reply FROM review_messages WHERE approval_id=? AND seq<? AND reply IS NOT NULL ORDER BY seq",
                (message["approval_id"], message["seq"]),
            )
            output = await self._request(
                parent["id"],
                PARENT_MODEL,
                "parent_discussion",
                {
                    "kind": "discussion",
                    "node_id": parent["id"],
                    "child_node_id": leaf["id"],
                    "goal": leaf["goal"],
                    "approval_id": approval["id"],
                    "version": message["version"],
                    "content_hash": message["content_hash"],
                    "artifact_type": approval["artifact_type"],
                    "artifact": approval["payload"],
                    "question": english,
                    "discussion_history": history,
                },
                ParentDiscussionResponse,
                "discussion:" + message_id,
            )
            reply = output.reply
            self.store.execute(
                "UPDATE review_messages SET reply=?,status='TRANSLATING' WHERE id=?",
                (reply, message_id),
            )
        translated = await self._request(
            "__user_translation__",
            PARENT_MODEL,
            "user_display",
            {
                "kind": "display_translation",
                "source_text": reply,
                "instruction": "Translate this reply for the Chinese human interface. Preserve every formula and LaTeX expression verbatim.",
            },
            UserDisplayTranslation,
            "display:" + message_id,
            validate=lambda output: preserve_math(reply, output.display_text),
        )
        display_reply = translated.display_text
        with self.store.transaction() as c:
            c.execute(
                "UPDATE review_messages SET status='COMPLETED',display_reply=?,completed_at=CURRENT_TIMESTAMP WHERE id=?",
                (display_reply, message_id),
            )
            self.store.event(
                "parent_question_answered",
                {"message_id": message_id, "approval_id": approval["id"]},
                c,
            )
        # Discussion deliberately changes no approval, round, prompt, or research state.

    async def _feedback(self, feedback_id):
        f = self.store.one("SELECT * FROM feedback WHERE id=?", (feedback_id,))
        a = self.store.one("SELECT * FROM approvals WHERE id=?", (f["approval_id"],))
        r = self.store.one("SELECT * FROM rounds WHERE id=?", (f["round_id"],))
        n = self.store.node(f["node_id"])
        parent = self.store.node(n["parent_id"])
        comment = f["english_comment"]
        if comment is None:
            comment = await self._translate_user(f["original_comment"], f["id"])
            self.store.execute(
                "UPDATE feedback SET english_comment=? WHERE id=?", (comment, f["id"])
            )
        out = await self._request(
            parent["id"],
            PARENT_MODEL,
            "user_feedback",
            {
                "kind": "feedback",
                "node_id": parent["id"],
                "child_node_id": n["id"],
                "round_id": r["id"],
                "artifact_type": a["artifact_type"],
                "artifact": a["payload"],
                "feedback": comment,
                "goal": n["goal"],
                "research_state": parent["research_state"],
            },
            ParentRoundResponse,
            "feedback:" + f["id"],
            expected={"child_node_id": n["id"], "responding_to_round_id": r["id"]},
        )
        if a["artifact_type"] == "prompt":
            self.store.revise_prompt(
                r["id"], out.next_prompt, feedback_id=f["id"], response=encode(out)
            )
        else:
            self._commit_parent(r["id"], parent["id"], out, feedback_id=f["id"])

    def set_review_mode(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError("Review mode must be boolean")
        with self.store.transaction() as c:
            previous = json.loads(
                c.execute(
                    "SELECT value FROM settings WHERE key='manual_review_enabled'"
                ).fetchone()[0]
            )
            c.execute(
                "UPDATE settings SET value=? WHERE key='manual_review_enabled'", (encode(enabled),)
            )
            self.store.event(
                "review_mode_changed",
                {
                    "previous": previous,
                    "enabled": enabled,
                    "notice": "Pending review gates automatically released."
                    if not enabled
                    else "Review applies to gates not yet crossed.",
                },
                c,
            )
            if not enabled:
                rows = c.execute(
                    "SELECT id,content_hash FROM approvals WHERE status='PENDING'"
                ).fetchall()
                for a in rows:
                    c.execute(
                        "UPDATE approvals SET status='AUTO_APPROVED',decision='auto',decided_at=CURRENT_TIMESTAMP WHERE id=?",
                        (a["id"],),
                    )
                    self.store.event("auto_approval", dict(a), c)
            elif not previous:
                # Reclaim only automatic gates whose consumers have not started. Never
                # cancel or repeat a turn that may already have reached the browser.
                rows = c.execute(
                    "SELECT a.*,r.stage FROM approvals a JOIN rounds r ON r.id=a.round_id "
                    "WHERE a.status='AUTO_APPROVED' AND "
                    "((a.artifact_type='prompt' AND r.stage='PROMPT_READY' AND a.version=r.prompt_version) "
                    "OR (a.artifact_type='report' AND r.stage='AWAITING_PARENT_RESPONSE'))"
                ).fetchall()
                for a in rows:
                    kind = a["artifact_type"]
                    operation = ("leaf:" if kind == "prompt" else "parent:") + a["round_id"]
                    if kind == "report" and operation in self._tasks:
                        continue
                    if c.execute(
                        "SELECT id FROM turns WHERE id LIKE ? AND status!='FAILED_NOT_SENT' LIMIT 1",
                        (operation + ":e%",),
                    ).fetchone():
                        continue
                    c.execute(
                        "UPDATE approvals SET status='PENDING',decision=NULL,decided_at=NULL,deferred=0 WHERE id=?",
                        (a["id"],),
                    )
                    c.execute(
                        "UPDATE rounds SET stage=?,report_accepted=CASE WHEN ? THEN 0 ELSE report_accepted END WHERE id=?",
                        (
                            "PROMPT_APPROVAL" if kind == "prompt" else "REPORT_APPROVAL",
                            kind == "report",
                            a["round_id"],
                        ),
                    )
                    self.store.event(
                        "review_gate_rearmed",
                        {
                            "approval_id": a["id"],
                            "content_hash": a["content_hash"],
                            "artifact_type": kind,
                        },
                        c,
                    )
        self.store.config.manual_review_enabled = enabled
        self.store.set_setting("config", self.store.config.model_dump(mode="json"))
        self._gates()

    def decide(self, approval_id, decision, content_hash, comment=""):
        if decision in ("ask_parent", "discuss"):
            return self.ask_parent(approval_id, content_hash, comment)
        if decision not in ("approve", "later", "request_revision"):
            raise ValueError("Decision must be approve, ask_parent, request_revision, or later")
        with self.store.transaction() as c:
            a = c.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
            if not a:
                raise ValueError("Unknown approval item")
            if a["content_hash"] != content_hash:
                raise ValueError(
                    "Content changed. Review the exact current version before approving."
                )
            if a["status"] == "APPROVED" and decision == "approve":
                return  # Local duplicate click is idempotent.
            if a["status"] != "PENDING":
                raise ValueError("This approval version is no longer pending")
            if decision == "later":
                c.execute("UPDATE approvals SET deferred=1 WHERE id=?", (approval_id,))
            elif decision == "approve":
                c.execute(
                    "UPDATE approvals SET status='APPROVED',decision='approve',decided_at=CURRENT_TIMESTAMP WHERE id=?",
                    (approval_id,),
                )
            else:
                if not comment.strip():
                    raise ValueError("Provide feedback for the parent")
                c.execute(
                    "UPDATE approvals SET status='REVISION_REQUESTED',decision='request_revision',decided_at=CURRENT_TIMESTAMP WHERE id=?",
                    (approval_id,),
                )
                c.execute(
                    "UPDATE rounds SET stage=? WHERE id=?",
                    (
                        "PROMPT_DISCUSSION"
                        if a["artifact_type"] == "prompt"
                        else "REPORT_DISCUSSION",
                        a["round_id"],
                    ),
                )
                c.execute(
                    "INSERT INTO feedback(id,approval_id,node_id,round_id,original_comment) VALUES(?,?,?,?,?)",
                    ("f-" + uuid4().hex, a["id"], a["node_id"], a["round_id"], comment),
                )
            self.store.event(
                "human_decision",
                {
                    "approval_id": approval_id,
                    "node_id": a["node_id"],
                    "round_id": a["round_id"],
                    "artifact_type": a["artifact_type"],
                    "version": a["version"],
                    "content_hash": content_hash,
                    "decision": decision,
                    "actor": "human",
                    "source": "HUMAN_APPROVED" if decision == "approve" else "HUMAN_REVIEW_ACTION",
                },
                c,
            )
        self._gates()

    def recover(self):
        owned = self._lockfile is not None
        self._acquire()
        try:
            return self._recover_state()
        finally:
            if not owned:
                fcntl.flock(self._lockfile, fcntl.LOCK_UN)
                self._lockfile.close()
                self._lockfile = None

    def _recover_state(self):
        # Recover explicit errors only. Pending manual turns keep their IDs and must be resolved, never resent as a new turn.
        errors = self.store.query("SELECT * FROM errors WHERE resolved=0")
        for error in errors:
            key = error["operation"]
            epoch = self.store.setting("retry:" + key, 0)
            attempts = self.store.query(
                "SELECT * FROM turns WHERE id LIKE ?", (f"{key}:e{epoch}:a%",)
            )
            # Unknown delivery resumes the same turn. Only exhausted *invalid* replies need a new repair epoch.
            if len(attempts) >= self.store.config.format_retries + 1 and all(
                t["raw_response"] is not None and t["status"] == "INVALID" for t in attempts
            ):
                self.store.set_setting("retry:" + key, epoch + 1)
        with self.store.transaction() as c:
            c.execute("UPDATE nodes SET runtime_state='OK' WHERE runtime_state='ERROR'")
            c.execute("UPDATE errors SET resolved=1 WHERE resolved=0")
            c.execute("UPDATE optional_jobs SET status='PENDING',error=NULL WHERE status='ERROR'")
            c.execute("UPDATE review_messages SET status='PENDING' WHERE status='ERROR'")
            c.execute("DELETE FROM settings WHERE key LIKE 'optional_error:%'")
            self.store.event("recovery", {"errors_released": len(errors)}, c)
        self._gates()
        self.store.build_report()
        return {
            "errors_released": len(errors),
            "pending_approvals": len(
                self.store.query("SELECT id FROM approvals WHERE status='PENDING'")
            ),
            "pending_turns": len(unresolved_turns(self.store)),
        }

    def _local_optional(self, job):
        current = self.store.one("SELECT status FROM optional_jobs WHERE id=?", (job["id"],))
        if current and current["status"] == "COMPLETED":
            return
        payload = json.loads(job["payload"])
        if job["kind"] == "section":
            self.store.update_section(job["actor_id"], payload, job_id=job["id"])
        elif job["kind"] == "tree":
            actor = self.store.node(job["actor_id"])
            node = self.store.node(payload["node_id"])
            if payload["node_id"] != actor["id"] and node["parent_id"] != actor["id"]:
                raise ValueError("Tree action is outside the coordinating node subtree boundary")
            action = payload["type"]
            if action == "split":
                self.store.split(
                    node["id"], payload["children"], actor_id=actor["id"], job_id=job["id"]
                )
            elif action == "reweight":
                self.store.reweight(node["id"], payload["weights"], job_id=job["id"])
            else:
                self.store.set_node_status(
                    node["id"],
                    {
                        "pause": "PAUSED",
                        "resume": "ACTIVE",
                        "complete": "COMPLETED",
                        "abandon": "ABANDONED",
                    }[action],
                    job_id=job["id"],
                )
        elif job["kind"] == "message":
            if (
                payload["sender_node_id"] != job["actor_id"]
                or not self.store.is_internal(job["actor_id"])
                or not self.store.is_internal(payload["recipient_node_id"])
            ):
                raise ValueError("Internal messages require an internal sender and recipient")
            self.store.execute(
                "INSERT OR IGNORE INTO messages(id,sender_node_id,recipient_node_id,message,evidence_reference,reason) VALUES(?,?,?,?,?,?)",
                (
                    job["id"],
                    payload["sender_node_id"],
                    payload["recipient_node_id"],
                    payload["message"],
                    payload["evidence_reference"],
                    payload["reason"],
                ),
            )
        self.store.execute("UPDATE optional_jobs SET status='COMPLETED' WHERE id=?", (job["id"],))

    async def _coordinate(self, actor_id, context, key, message_id=None):
        node = self.store.node(actor_id)
        out = await self._request(
            actor_id,
            PARENT_MODEL,
            "parent_coordination",
            {
                "kind": "coordination",
                "node_id": actor_id,
                "goal": node["goal"],
                "research_state": node["research_state"],
                **context,
            },
            CoordinationResponse,
            key,
        )
        with self.store.transaction() as c:
            self._queue_optional(actor_id, out, key, c)
            c.execute(
                "UPDATE nodes SET research_state=? WHERE id=?", (out.research_state, actor_id)
            )
            if message_id:
                c.execute("UPDATE messages SET status='DELIVERED' WHERE id=?", (message_id,))
        if "allocation" in context:
            self.store.set_setting(
                "allocation_notified:" + actor_id, context["allocation"]["leaf_capacity"]
            )

    async def tick(self):
        if self._closed:
            raise ValueError("Scheduler is closed")
        self._acquire()
        for key, task in list(self._tasks.items()):
            if task.done():
                task.result()
                del self._tasks[key]
        self._gates()
        changed = False
        if not self.store.children("root"):
            if (
                self.store.setting("project_status") == "ACTIVE"
                and self.store.node("root")["runtime_state"] != "ERROR"
            ):
                changed |= self._launch(
                    "bootstrap", self._bootstrap(), "root", operation="bootstrap:root"
                )
            await asyncio.sleep(0)
            return changed
        # P0 continues to discharge stored reports even while the project/node is paused.
        waiting = self.store.query(
            "SELECT r.*,n.parent_id,n.runtime_state FROM rounds r JOIN nodes n ON n.id=r.node_id WHERE r.stage='AWAITING_PARENT_RESPONSE' ORDER BY r.seq"
        )
        feedback = self.store.query(
            "SELECT f.*,n.runtime_state FROM feedback f JOIN nodes n ON n.id=f.node_id WHERE f.status='PENDING' ORDER BY f.created_at,f.id"
        )
        for r in waiting:
            if r["runtime_state"] != "ERROR":
                changed |= self._launch(
                    "parent:" + r["id"],
                    self._parent(r["id"]),
                    r["node_id"],
                    operation="parent:" + r["id"],
                )
        for f in feedback:
            if f["runtime_state"] != "ERROR":
                changed |= self._launch(
                    "feedback:" + f["id"],
                    self._feedback(f["id"]),
                    f["node_id"],
                    operation="feedback:" + f["id"],
                )
        # One human discussion at a time per parent, after already-queued mandatory decisions.
        p0_parents = {r["parent_id"] for r in waiting}
        p0_parents.update(self.store.node(f["node_id"])["parent_id"] for f in feedback)
        discussion_parents = set()
        for key in self._tasks:
            if key.startswith("discussion:"):
                message = self.store.one(
                    "SELECT node_id FROM review_messages WHERE id=?",
                    (key.removeprefix("discussion:"),),
                )
                if message:
                    discussion_parents.add(self.store.node(message["node_id"])["parent_id"])
        for message in self.store.query(
            "SELECT * FROM review_messages WHERE status IN ('PENDING','TRANSLATING') ORDER BY seq"
        ):
            parent_id = self.store.node(message["node_id"])["parent_id"]
            if parent_id in p0_parents or parent_id in discussion_parents:
                continue
            key = "discussion:" + message["id"]
            changed |= self._launch(
                key, self._discussion(message["id"]), message["node_id"], optional=True
            )
            discussion_parents.add(parent_id)
        # Short local optional mutations only when no parent response is queued.
        if (
            not waiting
            and not feedback
            and not any(k.startswith(("parent:", "feedback:")) for k in self._tasks)
        ):
            job = self.store.one(
                "SELECT * FROM optional_jobs WHERE status='PENDING' ORDER BY priority,created_at,id LIMIT 1"
            )
            if job:
                try:
                    self._local_optional(job)
                except Exception as exc:
                    self.store.execute(
                        "UPDATE optional_jobs SET status='ERROR',error=? WHERE id=?",
                        (str(exc), job["id"]),
                    )
                    self.store.execute(
                        "INSERT INTO errors(node_id,operation,message) VALUES(?,?,?)",
                        (job["actor_id"], job["id"], str(exc)),
                    )
                changed = True
        allocation = self.store.allocation()
        # Allocation contraction is applied only at an undispatched round boundary.
        for node in allocation.values():
            if (
                node["role"] != "Pro leaf"
                or node["status"] != "ACTIVE"
                or node["leaf_capacity"] > 0
            ):
                continue
            if not allocation[node["parent_id"]]["effective_active"]:
                continue
            round_ = self.store.one(
                "SELECT * FROM rounds WHERE node_id=? AND stage NOT IN ('RESPONDED','SUPERSEDED') ORDER BY seq DESC LIMIT 1",
                (node["id"],),
            )
            if round_ and round_["stage"] in ("PROMPT_READY", "PROMPT_APPROVAL"):
                self.store.set_node_status(node["id"], "PAUSED")
                self.store.event(
                    "capacity_pause", {"node_id": node["id"], "round_id": round_["id"]}
                )
                changed = True
        if changed:
            allocation = self.store.allocation()
        for node in allocation.values():
            if (
                node["role"] == "Extra High internal"
                and not self.store.setting("coordinator_ready:" + node["id"], True)
                and node["runtime_state"] != "ERROR"
            ):
                key = "restore:" + node["id"]
                changed |= self._launch(
                    key, self._restore_internal(node["id"]), node["id"], operation=key
                )
        # A round already sent always finishes, including after allocation reduction or pause.
        solving = self.store.query(
            "SELECT r.*,n.runtime_state FROM rounds r JOIN nodes n ON n.id=r.node_id WHERE r.stage='SOLVING' ORDER BY r.seq"
        )
        started = {key[5:] for key in self._tasks if key.startswith("leaf:")}
        occupied = len(solving)
        for r in solving:
            if r["runtime_state"] != "ERROR" and r["id"] not in started:
                changed |= self._launch(
                    "leaf:" + r["id"],
                    self._leaf(r["id"]),
                    r["node_id"],
                    operation="leaf:" + r["id"],
                )
        count = self.store.one("SELECT COUNT(*) AS n FROM parent_responses")["n"]
        limit_reached = (
            self._max_pairs is not None and count - self._baseline + len(solving) >= self._max_pairs
        )
        if self.store.setting("project_status") == "ACTIVE" and not limit_reached:
            ready = self.store.query(
                "SELECT r.*,n.runtime_state FROM rounds r JOIN nodes n ON n.id=r.node_id WHERE r.stage='PROMPT_READY' ORDER BY r.seq"
            )
            for r in ready:
                if occupied >= self.store.config.max_concurrent_pro_turns:
                    break
                n = allocation[r["node_id"]]
                if (
                    r["runtime_state"] == "ERROR"
                    or not n["effective_active"]
                    or n["role"] != "Pro leaf"
                    or n["leaf_capacity"] <= 0
                    or not self._ancestors_ready(n["id"])
                    or self._pending_control(n["id"])
                ):
                    continue
                if (
                    self._max_pairs is not None
                    and count - self._baseline + occupied >= self._max_pairs
                ):
                    break
                if "leaf:" + r["id"] not in self._tasks:
                    changed |= self._launch(
                        "leaf:" + r["id"],
                        self._leaf(r["id"]),
                        r["node_id"],
                        operation="leaf:" + r["id"],
                    )
                    occupied += 1
        # Saved, undispatched next prompts are safe boundaries, not unfinished reports.
        # Counting them as busy would permanently starve event-driven coordination.
        busy_parents = {
            self.store.node(r["node_id"])["parent_id"]
            for r in self.store.query(
                "SELECT * FROM rounds WHERE stage IN ('SOLVING','REPORT_APPROVAL','AWAITING_PARENT_RESPONSE')"
            )
        }
        # Newly launched coroutines have not necessarily persisted SOLVING yet.
        busy_parents.update(
            self.store.node(
                self.store.one("SELECT node_id FROM rounds WHERE id=?", (key[5:],))["node_id"]
            )["parent_id"]
            for key in self._tasks
            if key.startswith("leaf:")
        )
        if not waiting and not feedback:
            for msg in self.store.query(
                "SELECT * FROM messages WHERE status='PENDING' ORDER BY created_at,id"
            ):
                actor = msg["recipient_node_id"]
                if actor not in busy_parents and not self.store.setting(
                    "optional_error:message:" + msg["id"], False
                ):
                    key = "message:" + msg["id"]
                    changed |= self._launch(
                        key,
                        self._coordinate(actor, {"important_message": msg}, key, msg["id"]),
                        actor,
                        optional=True,
                    )
            for node in allocation.values():
                if (
                    node["role"] != "Extra High internal"
                    or node["id"] in busy_parents
                    or not node["effective_active"]
                ):
                    continue
                prior = self.store.setting("allocation_notified:" + node["id"])
                target = node["leaf_capacity"]
                if prior is None:
                    self.store.set_setting("allocation_notified:" + node["id"], target)
                elif abs(target - prior) >= 2:  # small deterministic hysteresis
                    key = f"allocation:{node['id']}:{target}"
                    if not self.store.setting("optional_error:" + key, False):
                        changed |= self._launch(
                            key,
                            self._coordinate(
                                node["id"],
                                {
                                    "allocation": {
                                        "leaf_capacity": target,
                                        "previous_capacity": prior,
                                        "unused_capacity": node["unused_capacity"],
                                    }
                                },
                                key,
                            ),
                            node["id"],
                            optional=True,
                        )
        # P2 assembly is local and only runs after queued P0 tasks have their next prompt.
        if not waiting and not feedback and self.store.setting("report_dirty"):
            self.store.build_report()
        await asyncio.sleep(0)
        return changed

    async def run(self, max_rounds=None):
        if max_rounds is not None and max_rounds < 1:
            raise ValueError("Round limit must be positive")
        self._baseline = self.store.one("SELECT COUNT(*) AS n FROM parent_responses")["n"]
        self._max_pairs = max_rounds
        try:
            while True:
                await self.tick()
                done = (
                    self.store.one("SELECT COUNT(*) AS n FROM parent_responses")["n"]
                    - self._baseline
                )
                if max_rounds is not None and done >= max_rounds:
                    break
                if max_rounds is not None and self.store.one(
                    "SELECT id FROM nodes WHERE runtime_state='ERROR'"
                ):
                    raise ValueError(
                        "Demo stopped with a recoverable error; inspect status and recover"
                    )
                await asyncio.sleep(0.05)
            # Finish local queued P1/P2 proposals without starting more research.
            for job in self.store.query(
                "SELECT * FROM optional_jobs WHERE status='PENDING' ORDER BY priority,created_at,id"
            ):
                try:
                    self._local_optional(job)
                except Exception as exc:
                    self.store.execute(
                        "UPDATE optional_jobs SET status='ERROR',error=? WHERE id=?",
                        (str(exc), job["id"]),
                    )
            self.store.build_report()
        finally:
            await self.aclose()

    def snapshot(self):
        allocation = self.store.allocation()
        nodes = list(allocation.values())
        rounds = self.store.query("SELECT * FROM rounds ORDER BY seq DESC LIMIT 100")
        responses = self.store.query(
            "SELECT * FROM parent_responses ORDER BY created_at DESC LIMIT 100"
        )
        for r in rounds:
            r["parent_response"] = next(
                (json.loads(x["payload"]) for x in responses if x["round_id"] == r["id"]), None
            )
        approvals = self.store.query(
            "SELECT a.*,n.parent_id FROM approvals a JOIN nodes n ON n.id=a.node_id WHERE a.status='PENDING' ORDER BY a.created_at,a.id"
        )
        settings = {
            "project_status": self.store.setting("project_status"),
            "manual_review_enabled": self.store.setting("manual_review_enabled"),
            "target_active_leaves": self.store.config.target_active_leaves,
            "max_active_leaves": self.store.config.max_active_leaves,
            "max_concurrent_pro_turns": self.store.config.max_concurrent_pro_turns,
        }
        return {
            "nodes": nodes,
            "approvals": approvals,
            "rounds": rounds,
            "parent_responses": responses,
            "messages": self.store.query(
                "SELECT * FROM messages ORDER BY created_at DESC LIMIT 50"
            ),
            "sessions": self.store.query("SELECT * FROM sessions"),
            "turns": self.store.query("SELECT * FROM turns ORDER BY created_at DESC LIMIT 50"),
            "errors": self.store.query("SELECT * FROM errors WHERE resolved=0 ORDER BY id DESC"),
            "optional_jobs": self.store.query(
                "SELECT * FROM optional_jobs WHERE status!='COMPLETED'"
            ),
            "feedback": self.store.query(
                "SELECT * FROM feedback ORDER BY created_at DESC LIMIT 50"
            ),
            "review_messages": self.store.query("SELECT * FROM review_messages ORDER BY seq"),
            "events": self.store.query("SELECT * FROM events ORDER BY id DESC LIMIT 40"),
            "settings": settings,
            "transport": self.transport.health()
            if hasattr(self.transport, "health")
            else {"mode": "custom", "live_verified": False},
            "report_path": str(self.store.root / "RESEARCH_REPORT.md"),
        }
