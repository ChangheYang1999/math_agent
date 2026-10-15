"""Persistent ChatGPT conversation boundary; never uses an inference API.

The scripted transport is an explicitly offline simulator. The manual relay is
usable without a browser bridge: it queues the exact prompt and accepts only a
human-pasted response. Neither implementation claims autonomous web access.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, uuid5

PRO_MODEL = "GPT-6 Pro"
COORDINATOR_MODEL = "GPT-6 Extra High"
MODELS = frozenset({PRO_MODEL, COORDINATOR_MODEL})


class TransportError(RuntimeError):
    """A recoverable conversation or transport problem."""


class RelayPending(TransportError):
    """A durable turn is waiting for a real response pasted by the human."""

    def __init__(self, turn_id: str) -> None:
        self.turn_id = turn_id
        super().__init__(f"Manual relay is waiting for a pasted ChatGPT response: {turn_id}")


@dataclass(frozen=True)
class Session:
    id: str
    node_id: str
    model: str
    url: str | None = None


class ChatGPTTransport(Protocol):
    async def create_session(self, node_id: str, model: str, idempotency_key: str) -> Session: ...

    async def send_message(self, session: Session, prompt: str, turn_id: str) -> None: ...

    async def await_response(self, session: Session, turn_id: str) -> str: ...


class _StoredTransport:
    def __init__(self, store: Any) -> None:
        self.store = store

    async def create_session(self, node_id: str, model: str, idempotency_key: str) -> Session:
        if model not in MODELS:
            raise TransportError(f"Unsupported ChatGPT UI model: {model}")
        if not node_id.strip() or not idempotency_key.strip():
            raise TransportError("Session node and idempotency key must be nonempty")
        session_id = "S-" + uuid5(NAMESPACE_URL, f"mathagent:{idempotency_key}").hex
        existing = self.store.one("SELECT * FROM sessions WHERE id=?", (session_id,))
        if existing is not None:
            session = _session(existing)
            if (session.node_id, session.model) != (node_id, model):
                raise TransportError("Session idempotency key is bound to another node or model")
            return session
        # Reuse a persistent chat for a node of the same role. A promotion gets
        # a new session while preserving the previous session as an audit row.
        current = self.store.one(
            "SELECT * FROM sessions WHERE node_id=? AND model=? AND active=1 "
            "ORDER BY created_at DESC LIMIT 1",
            (node_id, model),
        )
        if current is not None:
            return _session(current)
        with self.store.transaction() as connection:
            connection.execute("UPDATE sessions SET active=0 WHERE node_id=?", (node_id,))
            connection.execute(
                "INSERT INTO sessions(id,node_id,model,url,active,created_at) "
                "VALUES(?,?,?,NULL,1,CURRENT_TIMESTAMP)",
                (session_id, node_id, model),
            )
        return Session(session_id, node_id, model)

    def get_session(self, session_id: str) -> Session:
        row = self.store.one("SELECT * FROM sessions WHERE id=?", (session_id,))
        if row is None:
            raise TransportError(f"Unknown ChatGPT session: {session_id}")
        return _session(row)

    async def recover_session(self, session_id: str) -> Session:
        return self.get_session(session_id)

    async def rollover_session(self, session_id: str, idempotency_key: str) -> Session:
        """Keep the old mapping for audit and start an unbound replacement chat.

        The caller must bootstrap the new conversation from durable node state.
        """
        previous = self.get_session(session_id)
        replacement_id = "S-" + uuid5(NAMESPACE_URL, f"mathagent:{idempotency_key}").hex
        if replacement_id == session_id:
            raise TransportError("Context rollover requires a new session idempotency key")
        self.store.execute("UPDATE sessions SET active=0 WHERE id=?", (session_id,))
        return await self.create_session(previous.node_id, previous.model, idempotency_key)

    def _queue(self, session: Session, prompt: str, turn_id: str) -> bool:
        if not prompt.strip() or not turn_id.strip():
            raise TransportError("Turn ID and exact prompt must be nonempty")
        stored_session = self.get_session(session.id)
        if (stored_session.node_id, stored_session.model) != (session.node_id, session.model):
            raise TransportError("Conversation binding does not match the stored session")
        row = self.store.one("SELECT * FROM turns WHERE id=?", (turn_id,))
        if row is not None:
            if row["session_id"] != session.id or row["prompt"] != prompt:
                raise TransportError("Turn ID cannot be reused with changed prompt or conversation")
            return False
        self.store.execute(
            "INSERT INTO turns(id,session_id,prompt,status,created_at) "
            "VALUES(?,?,?,'QUEUED',CURRENT_TIMESTAMP)",
            (turn_id, session.id, prompt),
        )
        return True

    def _turn(self, session: Session, turn_id: str) -> Any:
        row = self.store.one("SELECT * FROM turns WHERE id=?", (turn_id,))
        if row is None or row["session_id"] != session.id:
            raise TransportError(f"Unknown turn for this conversation: {turn_id}")
        return row


class ScriptedTransport(_StoredTransport):
    """Deterministic offline responses exercising the real scheduler.

    ``script`` may be a callable receiving the appended context dictionary, a
    sequence, or a mapping from turn kind to sequences/callables. Sequence items
    may be JSON dictionaries, raw strings, exceptions, or context callables.
    Already persisted raw replies are returned without consuming another item.
    """

    def __init__(
        self,
        store: Any,
        script: Callable[..., Any] | Sequence[Any] | Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(store)
        self.script = script
        self.calls: list[dict[str, Any]] = []
        self.sent: list[dict[str, Any]] = []
        self._offsets: dict[str, int] = {}

    async def send_message(self, session: Session, prompt: str, turn_id: str) -> None:
        previous = self.store.one("SELECT * FROM turns WHERE id=?", (turn_id,))
        inserted = self._queue(session, prompt, turn_id)
        if inserted or (
            previous is not None
            and previous["raw_response"] is None
            and previous["status"] not in {"SENT", "COMPLETED"}
        ):
            self.sent.append(_call(session, prompt, turn_id))
        self.store.execute(
            "UPDATE turns SET status='SENT' WHERE id=? AND raw_response IS NULL", (turn_id,)
        )

    async def await_response(self, session: Session, turn_id: str) -> str:
        row = self._turn(session, turn_id)
        if row["raw_response"] is not None:
            return str(row["raw_response"])
        call = _call(session, row["prompt"], turn_id)
        self.calls.append(call)
        context = call["context"]
        selected = self.script
        key = "*"
        if isinstance(selected, Mapping):
            key = str(context.get("kind", ""))
            selected = selected.get(turn_id, selected.get(key))
        if selected is None:
            value = _default_response(context)
        elif callable(selected):
            value = selected(context)
        elif isinstance(selected, Sequence) and not isinstance(selected, str | bytes):
            offset = self._offsets.get(key, 0)
            if offset >= len(selected):
                raise TransportError(f"Offline script exhausted for {key}")
            self._offsets[key] = offset + 1
            value = selected[offset]
            if callable(value):
                value = value(context)
        else:
            value = selected
        if inspect.isawaitable(value):
            value = await value
        if isinstance(value, BaseException):
            raise value
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=True)
        self.store.execute(
            "UPDATE turns SET raw_response=?,status='COMPLETED',error=NULL WHERE id=?",
            (raw, turn_id),
        )
        return raw

    def health(self) -> dict[str, Any]:
        return {
            "mode": "scripted",
            "autonomous": False,
            "live_verified": False,
            "available": True,
            "detail": "Offline simulation only; no ChatGPT web requests are made.",
            "reason": "Offline simulation only; no ChatGPT web requests are made.",
        }


class ManualRelayTransport(_StoredTransport):
    """Persistent copy/paste relay with explicit model and conversation binding."""

    async def send_message(self, session: Session, prompt: str, turn_id: str) -> None:
        self._queue(session, prompt, turn_id)

    async def await_response(self, session: Session, turn_id: str) -> str:
        row = self._turn(session, turn_id)
        if row["raw_response"] is None:
            raise RelayPending(turn_id)
        return str(row["raw_response"])

    def bind_session(self, session_id: str, url: str, model: str) -> Session:
        session = self.get_session(session_id)
        if model != session.model:
            raise TransportError(
                f"Select exactly {session.model} in ChatGPT; model fallback is not allowed"
            )
        parsed = urlparse(url.strip())
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"chatgpt.com", "chat.openai.com"}
            or "/c/" not in parsed.path
            or not parsed.path.rsplit("/c/", 1)[-1].strip("/")
        ):
            raise TransportError("Bind a persistent https://chatgpt.com/c/... conversation URL")
        if session.url and session.url != url.strip():
            raise TransportError(
                "A bound conversation cannot be replaced; create a new session for rollover"
            )
        other = self.store.one(
            "SELECT id FROM sessions WHERE url=? AND id!=?", (url.strip(), session_id)
        )
        if other is not None:
            raise TransportError(
                "Each research session requires its own distinct ChatGPT conversation"
            )
        self.store.execute("UPDATE sessions SET url=? WHERE id=?", (url.strip(), session_id))
        return self.get_session(session_id)

    def list_pending(self) -> list[dict[str, Any]]:
        from .recovery import unresolved_turns

        unresolved = {turn["id"] for turn in unresolved_turns(self.store)}
        return [
            dict(row)
            for row in self.store.query(
                "SELECT turns.*,sessions.node_id,sessions.model,sessions.url "
                "FROM turns JOIN sessions ON sessions.id=turns.session_id "
                "WHERE turns.raw_response IS NULL AND turns.status!='FAILED_NOT_SENT' ORDER BY turns.created_at,turns.id"
            )
            if row["id"] in unresolved
        ]

    def mark_sent(self, turn_id: str) -> None:
        row = self._bound_turn(turn_id)
        if row["raw_response"] is None:
            self.store.execute("UPDATE turns SET status='SENT' WHERE id=?", (turn_id,))

    def submit_response(self, turn_id: str, raw_response: str) -> None:
        if not raw_response.strip():
            raise TransportError("Paste the actual complete ChatGPT response")
        row = self._bound_turn(turn_id)
        if row["raw_response"] is not None:
            if row["raw_response"] != raw_response:
                raise TransportError("A stored raw response is immutable; use a new repair turn")
            return
        self.store.execute(
            "UPDATE turns SET raw_response=?,status='COMPLETED',error=NULL WHERE id=?",
            (raw_response, turn_id),
        )

    def _bound_turn(self, turn_id: str) -> Any:
        row = self.store.one(
            "SELECT turns.*,sessions.url FROM turns "
            "JOIN sessions ON sessions.id=turns.session_id WHERE turns.id=?",
            (turn_id,),
        )
        if row is None:
            raise TransportError(f"Unknown relay turn: {turn_id}")
        if not row["url"]:
            raise TransportError(
                "Bind the ChatGPT conversation URL and confirm its exact model first"
            )
        return row

    def health(self) -> dict[str, Any]:
        reason = (
            "Manual relay is selected. "
            "Copy each queued prompt into its bound ChatGPT conversation and paste the reply. "
            "Turning human review off does not automate manual relay."
        )
        return {
            "mode": "manual",
            "autonomous": False,
            "live_verified": False,
            "available": True,
            "pending_turns": len(self.list_pending()),
            "detail": reason,
            "reason": reason,
        }


def _session(row: Any) -> Session:
    return Session(row["id"], row["node_id"], row["model"], row["url"])


def _context(prompt: str) -> dict[str, Any]:
    marker = "\nCONTEXT_JSON\n"
    if marker not in prompt:
        return {}
    raw = prompt.rsplit(marker, 1)[-1].split("\nOUTPUT_SCHEMA_JSON\n", 1)[0].strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TransportError("Offline prompt has invalid CONTEXT_JSON") from exc
    if not isinstance(result, dict):
        raise TransportError("Offline prompt context must be a JSON object")
    return result


def _call(session: Session, prompt: str, turn_id: str) -> dict[str, Any]:
    return {
        "session_id": session.id,
        "node_id": session.node_id,
        "model": session.model,
        "turn_id": turn_id,
        "prompt": prompt,
        "context": _context(prompt),
    }


def _default_response(context: dict[str, Any]) -> dict[str, Any]:
    kind = context.get("kind")
    goal = str(context.get("goal", "Study the assigned mathematical problem"))
    if kind == "discussion":
        return {
            "reply": "Offline parent discussion: the artifact remains pending. Check the stated assumptions and evidence; use Request Revision for an explicit change. This reply does not approve or schedule any research."
        }
    if kind == "display_translation":
        return {
            "display_text": "离线家长讨论演示：请核查假设与证据。此回答不会批准内容，也不会启动研究；如需修改，请选择请求修改。英文原文保留在讨论历史中。"
        }
    if kind == "bootstrap":
        existing = context.get("existing_children")
        if existing:
            return {
                "research_state": (
                    "Offline coordinator restoration: preserve the durable goals and shares, "
                    "then validate the existing concrete child tasks before dispatch."
                ),
                "children": [
                    {
                        "goal": child["goal"],
                        "relative_weight": child["relative_weight"],
                        "initial_prompt": child.get("initial_prompt")
                        or child.get("task")
                        or (
                            f"Investigate the assigned subproblem: {child['goal']}. State all "
                            "hypotheses, verify a precise partial result and its boundary cases, "
                            "and return one structured report with rigorous evidence and obstacles."
                        ),
                    }
                    for child in existing
                ],
            }
        return {
            "research_state": "Offline demo: investigate one concrete task before further decomposition.",
            "children": [
                {
                    "goal": goal,
                    "relative_weight": 1.0,
                    "initial_prompt": (
                        f"Investigate this precise task: {goal}. State the domain and hypotheses, "
                        "derive a rigorous partial result or proof, test equality or boundary cases, "
                        "and identify any gap. Return one structured report for the assigned round."
                    ),
                }
            ],
        }
    if kind == "leaf":
        # A useful, explicitly synthetic elementary example. Unrelated goals do
        # not receive a fabricated proof of their requested theorem.
        task = str(context.get("task", ""))
        demo = any(
            token in (goal + " " + task).lower()
            for token in (
                "cauchy",
                "x^2 + y^2",
                "x² + y²",
                "square",
                "quadratic",
                "nonnegative",
            )
        )
        return {
            "node_id": context["node_id"],
            "round_id": context["round_id"],
            "status": "PARTIAL" if demo else "STUCK",
            "summary": (
                "Offline demo: established the elementary inequality 2xy <= x^2+y^2."
                if demo
                else "Offline simulation has no mathematical solver for this task."
            ),
            "findings": ["For real x,y, 2xy <= x^2+y^2 with equality exactly when x=y."]
            if demo
            else [],
            "evidence": (
                "For real x,y, (x-y)^2 >= 0. Expanding and rearranging yields "
                "x^2+y^2-2xy >= 0; equality holds exactly when x-y=0. "
                "This is scripted demonstration text, not a verified ChatGPT web result."
                if demo
                else "No live ChatGPT conversation was contacted; no claim was proved."
            ),
            "obstacles": ["Independent checking of model-proposed results is still required."],
            "recommended_next_steps": [
                "Independently verify the derivation and all equality cases."
            ],
            "split_suggestion": [],
            "important_update": demo and str(context["round_id"]).endswith("000001"),
        }
    if kind in {"parent", "feedback"}:
        report = context.get("report") or {}
        if isinstance(report, str):
            try:
                report = json.loads(report)
            except json.JSONDecodeError:
                report = {}
        child_id = context.get("child_node_id", report.get("node_id", context.get("node_id")))
        round_id = context.get(
            "round_id", context.get("responding_to_round_id", report.get("round_id"))
        )
        return {
            "child_node_id": child_id,
            "responding_to_round_id": round_id,
            "assessment": (
                "Offline parent simulation: human feedback requires a revised verification task; "
                "this discussion does not approve the original artifact."
                if kind == "feedback"
                else "Offline parent simulation: retain the report and examine the proof gaps and equality cases."
            ),
            "next_prompt": (
                f"For the assigned goal '{goal}', independently check the previous report line by "
                "line. State each assumption, verify all algebraic steps and boundary/equality "
                "cases, and give either a corrected proof or a precise remaining obstruction. "
                "Address the parent's latest review feedback. Produce one structured LeafRoundReport "
                "bound to the exact new round ID; do not begin any additional round."
            ),
            "proposed_tree_actions": [],
            "proposed_messages": [],
            "proposed_report_updates": [],
        }
    if kind == "coordination":
        return {
            "research_state": "Optional coordination examined; no scientifically useful change is proposed.",
            "proposed_tree_actions": [],
            "proposed_messages": [],
            "proposed_report_updates": [],
        }
    if kind == "translation":
        return {
            "english_text": (
                "Offline translation simulation: the human requests clarification or revision of the "
                "current artifact. This placeholder is not a live translation; use scripted translated "
                "text in tests or paste an actual translation through manual relay."
            )
        }
    if kind == "report_update":
        return {
            "node_id": context["node_id"],
            "body": "No significant publishable finding was established in this offline simulation.",
            "claim_status": "MODEL_PROPOSED",
            "significant": False,
            "evidence_reference": str(context.get("round_id", "offline")),
            "independent_verification": "",
        }
    raise TransportError(f"No offline response for context kind: {kind}")
