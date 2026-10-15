"""Browser-backed transport for DrA1ex/chatgpt-bridge's durable HTTP turns.

Verified against upstream 0ffdae90239988f253058c05253226152acd55d2:
routes.js, turnManager.js, http/publicTurnStream.js and extension session/model
commands. Unlike /chat, /turns persists an explicit request ID and its terminal
result. We never replay a POST after uncertain delivery, even with a key.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import quote, urlparse
from uuid import NAMESPACE_URL, uuid5

import httpx

from .recovery import unresolved_turns
from .transport import COORDINATOR_MODEL, PRO_MODEL, TransportError, _StoredTransport


class BridgeTransport(_StoredTransport):
    def __init__(self, store: Any, *, http_transport=None) -> None:
        super().__init__(store)
        self.config = store.config
        self.base_url = os.getenv("MATHAGENT_BRIDGE_BASE_URL", self.config.bridge_base_url).rstrip(
            "/"
        )
        parsed = urlparse(self.base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise TransportError("Configure a valid bridge HTTP URL without embedded credentials")
        self._http_transport = http_transport
        self._token = os.getenv("MATHAGENT_BRIDGE_API_TOKEN", "")
        self._control_lock = asyncio.Lock()
        self._locks: dict[str, asyncio.Lock] = {}
        self._verified_roles: set[str] = set()
        self._completed_roles: set[str] = set()
        self._health = {
            "mode": "bridge",
            "base_url": self.base_url,
            "available": False,
            "connected": False,
            "autonomous": False,
            "live_verified": False,
            "models_verified": False,
            "detail": "Bridge has not been diagnosed in this process.",
        }

    @asynccontextmanager
    async def _client(self):
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            transport=self._http_transport,
            timeout=self.config.bridge_request_timeout,
            trust_env=False,
        ) as client:
            yield client

    async def _json(self, method, path, *, allow_not_ok=False, **kwargs):
        try:
            async with self._client() as client:
                response = await client.request(method, path, **kwargs)
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, dict) or (result.get("ok") is False and not allow_not_ok):
                    raise TransportError("Bridge returned an invalid or unsuccessful response")
                return result
        except (httpx.HTTPError, ValueError) as exc:
            status = (
                f" (HTTP {exc.response.status_code})"
                if isinstance(exc, httpx.HTTPStatusError)
                else ""
            )
            self._health.update(
                available=False,
                autonomous=False,
                detail=f"Bridge request failed: {type(exc).__name__}{status}",
            )
            raise TransportError(self._health["detail"]) from exc

    def health(self):
        result = dict(self._health)
        result["reason"] = result["detail"]
        result["verified_roles"] = sorted(self._verified_roles)
        result["completed_roles"] = sorted(self._completed_roles)
        result["uncertain_turns"] = len(
            self.store.query("SELECT id FROM turns WHERE status='UNCERTAIN'")
        )
        return result

    async def diagnose(self):
        """Read current connectivity and visible options; never submit a prompt."""
        try:
            health = await self._json("GET", "/health", allow_not_ok=True)
            clients = await self._json("GET", "/browser/clients")
            connected = [c for c in clients.get("clients", []) if _compatible(c)]
            self._health.update(
                connected=bool(connected), clients=len(connected), bridge_ok=health.get("ok", False)
            )
            if not connected:
                raise TransportError(
                    "No compatible ChatGPT extension tab is connected; log in and connect the extension."
                )
            models = await self._json("GET", "/models")
            efforts = await self._json("GET", "/efforts")
            sessions = await self._json("GET", "/sessions")
            self._health.update(
                models=models.get("models", []),
                efforts=efforts.get("efforts", []),
                current_model=models.get("current"),
                current_effort=efforts.get("current"),
                sessions=len(sessions.get("sessions", [])),
            )
            pro = _configured_model(
                models.get("models", []), self.config.bridge_pro_model, PRO_MODEL
            )
            parent = _configured_model(
                models.get("models", []), self.config.bridge_parent_model, COORDINATOR_MODEL
            )
            effort = _option(efforts.get("efforts", []), self.config.bridge_parent_effort)
            pro_effort = next((o for o in efforts.get("efforts", []) if _pro_effort(o)), None)
            available = bool(
                pro
                and parent
                and (_role_model(pro, PRO_MODEL) or pro_effort or PRO_MODEL in self._verified_roles)
                and ((effort and _extra_high(effort)) or COORDINATOR_MODEL in self._verified_roles)
            )
            self._health.update(
                available=available,
                autonomous=available and len(self._verified_roles) == 2,
                detail=(
                    "Bridge connected; role options observed. Each bound tab must have its exact model/intelligence selected before dispatch."
                    if available
                    else "SELECTION_REQUIRED: the selected tab does not expose both role proofs. In each bound tab choose GPT-6, then Pro for a leaf or Extra High for a coordinator; verify before dispatch. Current effort alone does not establish Pro availability."
                ),
            )
        except TransportError as exc:
            self._health.update(available=False, autonomous=False, detail=str(exc))
        return self.health()

    async def create_session(self, node_id, model, idempotency_key):
        # A rollover keeps the original idempotency row as inactive history.
        # Prefer its active replacement instead of resurrecting the old chat.
        if not idempotency_key.strip():
            raise TransportError("Session idempotency key must be nonempty")
        key_id = "S-" + uuid5(NAMESPACE_URL, f"mathagent:{idempotency_key}").hex
        claimed = self.store.one("SELECT * FROM sessions WHERE id=?", (key_id,))
        if claimed and (claimed["node_id"], claimed["model"]) != (node_id, model):
            raise TransportError("Session idempotency key belongs to another node or model")
        current = self.store.one(
            "SELECT id FROM sessions WHERE node_id=? AND model=? AND active=1 ORDER BY created_at DESC LIMIT 1",
            (node_id, model),
        )
        session = (
            self.get_session(current["id"])
            if current
            else await super().create_session(node_id, model, idempotency_key)
        )
        async with self._control_lock:
            await self._binding(session)
        return self.get_session(session.id)

    async def recover_session(self, session_id):
        session = self.get_session(session_id)
        async with self._control_lock:
            await self._binding(session)
        return self.get_session(session_id)

    async def _binding(self, session):
        row = self.store.one("SELECT * FROM sessions WHERE id=?", (session.id,))
        # A browser can disappear while its durable server turn completes.
        # Reconcile using the original identity before changing the tab binding.
        if row["bridge_client_id"] and any(
            turn["bridge_request_id"] for turn in unresolved_turns(self.store, session.id)
        ):
            return row
        clients = (await self._json("GET", "/browser/clients")).get("clients", [])
        launch_token = "bridge-mathagent-" + uuid5(NAMESPACE_URL, session.id).hex
        matches = [
            c
            for c in clients
            if _compatible(c)
            and (
                c.get("id") == row["bridge_client_id"]
                or (row["bridge_session_id"] and _conversation(c) == row["bridge_session_id"])
                or (row["bridge_state"] == "CREATING" and c.get("launchToken") == launch_token)
            )
        ]
        if len(matches) > 1:
            raise TransportError(
                "Multiple tabs match this conversation; select one explicitly in Bridge."
            )
        if matches:
            client = matches[0]
            actual = _conversation(client)
            if row["bridge_session_id"] and actual != row["bridge_session_id"]:
                raise TransportError(
                    "Bound browser tab moved to another conversation; restore the saved URL."
                )
        else:
            if row["bridge_state"] == "CREATING":
                raise TransportError(
                    "UNCERTAIN tab creation: inspect Bridge tabs before replacing the unconfirmed binding."
                )
            self.store.execute(
                "UPDATE sessions SET bridge_state='CREATING' WHERE id=?", (session.id,)
            )
            opened = await self._json(
                "POST",
                "/browser/tabs/open",
                json={
                    "url": row["url"] if row["bridge_session_id"] else "https://chatgpt.com/",
                    "active": False,
                    "select": False,
                    "launchToken": launch_token,
                },
            )
            client = opened.get("client", {})
            if not _compatible(client) or not client.get("id"):
                raise TransportError("Bridge did not prove a dedicated connected browser tab")
            actual = _conversation(client)
            if row["bridge_session_id"] and actual != row["bridge_session_id"]:
                raise TransportError("Reopened tab did not prove the saved conversation identity")
        try:
            self.store.execute(
                "UPDATE sessions SET bridge_client_id=?,bridge_state='BOUND' WHERE id=?",
                (client["id"], session.id),
            )
        except Exception as exc:
            raise TransportError(
                "A browser tab is already bound to a different active node"
            ) from exc
        return self.store.one("SELECT * FROM sessions WHERE id=?", (session.id,))

    async def _selection(self, session):
        # Discovery APIs operate on the selected client, so serialize selection
        # and discovery; actual requests carry a strict sourceClientId.
        async with self._control_lock:
            row = await self._binding(session)
            await self._json("POST", "/browser/select", json={"clientId": row["bridge_client_id"]})
            models = await self._json("GET", "/models")
            required = (
                self.config.bridge_pro_model
                if session.model == PRO_MODEL
                else self.config.bridge_parent_model
            )
            chosen = _configured_model(models.get("models", []), required, session.model)
            if not chosen or not _same(models.get("current"), chosen):
                raise TransportError(
                    f"MODEL_UNAVAILABLE: select exactly {required} in node {session.node_id}'s bound ChatGPT tab; no prompt was sent."
                )
            effort_id = ""
            # The current UI represents GPT-6 Pro as GPT-6 + Pro intelligence.
            # A dedicated exact Pro model in the older picker remains supported.
            needs_pro_effort = session.model == PRO_MODEL and not _role_model(chosen, PRO_MODEL)
            if session.model == COORDINATOR_MODEL or needs_pro_effort:
                efforts = await self._json("GET", "/efforts")
                selected = (
                    next((o for o in efforts.get("efforts", []) if _pro_effort(o)), None)
                    if needs_pro_effort
                    else _option(efforts.get("efforts", []), self.config.bridge_parent_effort)
                )
                if (
                    not selected
                    or not (_pro_effort(selected) if needs_pro_effort else _extra_high(selected))
                    or not _same(efforts.get("current"), selected)
                ):
                    tier = "Pro (fifth intelligence level)" if needs_pro_effort else "Extra High"
                    raise TransportError(
                        f"MODEL_UNAVAILABLE: select {tier} in node {session.node_id}'s bound GPT-6 tab; no prompt was sent."
                    )
                effort_id = selected.get("id") or selected["label"]
            model_id = chosen.get("id") or chosen["label"]
            self.store.execute(
                "UPDATE sessions SET bridge_model=?,bridge_effort=? WHERE id=?",
                (model_id, effort_id, session.id),
            )
            self._verified_roles.add(session.model)
            both_roles = len(self._verified_roles) == 2
            self._health.update(
                connected=True,
                available=True,
                autonomous=both_roles,
                models_verified=both_roles,
                detail="Exact model/effort verified before dispatch for: "
                + ", ".join(sorted(self._verified_roles)),
            )
            return row, model_id, effort_id

    def _request_id(self, turn_id):
        return "mathagent_" + uuid5(NAMESPACE_URL, f"{self.store.path}:{turn_id}").hex

    async def send_message(self, session, prompt, turn_id):
        async with self._locks.setdefault(session.id, asyncio.Lock()):
            self._queue(session, prompt, turn_id)
            if prompt != prompt.strip():
                message = "Bridge trims outer whitespace; revise and approve an exact prompt without surrounding whitespace before dispatch."
                self.store.execute(
                    "UPDATE turns SET status='QUEUED',error=? WHERE id=?", (message, turn_id)
                )
                raise TransportError(message)
            turn = self._turn(session, turn_id)
            if turn["raw_response"] is not None:
                return
            if turn["bridge_request_id"] or turn["status"] in {"SENDING", "SENT", "UNCERTAIN"}:
                await self._reconcile(session, turn_id)
                return
            other = next(iter(unresolved_turns(self.store, session.id, turn_id)), None)
            if other:
                raise TransportError(f"Conversation has another unresolved turn: {other['id']}")
            try:
                row, model, effort = await self._selection(session)
            except TransportError as exc:
                # This failure is known to be before the message POST, so an
                # explicit scheduler recovery may safely retry the same turn.
                self.store.execute(
                    "UPDATE turns SET status='QUEUED',error=? WHERE id=?", (str(exc), turn_id)
                )
                raise
            request_id = self._request_id(turn_id)
            self.store.execute(
                "UPDATE turns SET status='SENDING',bridge_request_id=?,error=NULL WHERE id=?",
                (request_id, turn_id),
            )
            # Upstream picker matching is fuzzy ("high" matches "xhigh"). Empty
            # selectors are proven no-ops in requestPreparation.applyModelOptions;
            # never let that selector alter our exactly verified bound tab.
            body = {
                "id": request_id,
                "message": prompt,
                "model": "",
                "effort": "",
                "sourceClientId": row["bridge_client_id"],
                "sessionPolicy": "reuse",
                "sessionId": row["bridge_session_id"] or "",
                "output": {"expected": "text", "required": False},
                "metadata": {
                    "researchNodeId": session.node_id,
                    "requiredModel": model,
                    "requiredEffort": effort,
                },
            }
            try:
                result = await self._json(
                    "POST", "/turns", json=body, headers={"Idempotency-Key": request_id}
                )
                self._validate_upstream(result.get("turn", {}), session, turn_id)
                self.store.execute("UPDATE turns SET status='SENT' WHERE id=?", (turn_id,))
            except BaseException:
                self._uncertain(
                    turn_id,
                    "Dispatch acknowledgement was lost or mismatched; reconcile the durable Bridge turn before any resend.",
                )
                raise

    def _uncertain(self, turn_id, message):
        self.store.execute(
            "UPDATE turns SET status='UNCERTAIN',error=? WHERE id=? AND raw_response IS NULL",
            (message, turn_id),
        )

    async def acknowledge_undelivered_failure(self, session, turn_id, *, blocking_request_id=None):
        """Explicitly close a proven pre-dispatch busy failure without retrying it.

        Unknown delivery, model holds and any browser delivery/effect evidence
        remain blocking. A new approved turn must use a new durable identity.
        """
        async with self._locks.setdefault(session.id, asyncio.Lock()):
            local = self._turn(session, turn_id)
            if local["status"] == "FAILED_NOT_SENT":
                return {"turn_id": turn_id, "status": "FAILED_NOT_SENT"}
            if (
                local["status"] != "ERROR"
                or local["raw_response"] is not None
                or not local["bridge_request_id"]
            ):
                raise TransportError(
                    "Only a known terminal error can be acknowledged as undelivered"
                )
            request_id = local["bridge_request_id"]
            path = "/turns/" + quote(request_id, safe="")
            upstream = (await self._json("GET", path)).get("turn", {})
            self._validate_upstream(upstream, session, turn_id)
            binding = self.store.one("SELECT * FROM sessions WHERE id=?", (session.id,))
            message = f"Browser extension client {binding['bridge_client_id']} is busy with another local request."
            if blocking_request_id is not None:
                prior = self.store.query(
                    "SELECT * FROM turns WHERE session_id=? AND bridge_request_id=?",
                    (session.id, blocking_request_id),
                )
                unresolved = {row["id"] for row in unresolved_turns(self.store, session.id)}
                if (
                    len(prior) != 1
                    or prior[0]["id"] == turn_id
                    or prior[0]["status"] != "ERROR"
                    or prior[0]["raw_response"] is not None
                    or prior[0]["id"] in unresolved
                ):
                    raise TransportError(
                        "Exact blocking request requires its committed source-recovery receipt"
                    )
                message = f"Browser extension client {binding['bridge_client_id']} is busy with {blocking_request_id}."
            error = upstream.get("error") or {}
            if (
                upstream.get("status") != "failed"
                or upstream.get("output") is not None
                or error.get("code") != "failed"
                or error.get("message") != message
            ):
                raise TransportError("Bridge failure is not a proven pre-dispatch busy rejection")
            events = (await self._json("GET", path + "/events", params={"limit": 5000})).get(
                "events"
            )
            allowed = {
                "turn/queued",
                "turn/started",
                "request.started",
                "client.release.wait_started",
                "client.release.wait_completed",
                "request.deadline.scheduled",
                "request.error",
                "turn/failed",
            }
            if (
                not isinstance(events, list)
                or len(events) < 5
                or len(events) >= 5000
                or events[0].get("type") != "turn/queued"
                or events[-1].get("type") != "turn/failed"
                or any(e.get("type") not in allowed for e in events)
            ):
                raise TransportError(
                    "Incomplete or delivered Bridge turn evidence cannot release this failure"
                )
            for event in events:
                data = event.get("data") or {}
                if (
                    data.get("requestId", request_id) != request_id
                    or data.get("turnId", request_id) != request_id
                ):
                    raise TransportError("Bridge failure events belong to another request")
            failures = [e.get("data", {}) for e in events if e.get("type") == "request.error"]
            terminal = events[-1].get("data", {}).get("turn") or {}
            if (
                len(failures) != 1
                or failures[0].get("message") != message
                or failures[0].get("code") != "failed"
                or terminal.get("id") != request_id
                or terminal.get("status") != "failed"
                or terminal.get("error", {}).get("message") != message
                or sum(e.get("type") == "request.started" for e in events) != 1
            ):
                raise TransportError(
                    "Bridge failure events do not prove the exact undelivered turn"
                )
            with self.store.transaction() as c:
                updated = c.execute(
                    "UPDATE turns SET status='FAILED_NOT_SENT' WHERE id=? AND status='ERROR' AND raw_response IS NULL",
                    (turn_id,),
                )
                if updated.rowcount != 1:
                    raise TransportError("Turn changed while acknowledging its failure")
                self.store.event(
                    "bridge_undelivered_failure_acknowledged",
                    {
                        "turn_id": turn_id,
                        "request_id": request_id,
                        "blocking_request_id": blocking_request_id,
                        "turn": upstream,
                        "events": events,
                    },
                    c,
                )
            return {"turn_id": turn_id, "request_id": request_id, "status": "FAILED_NOT_SENT"}

    def _validate_upstream(self, upstream, session, turn_id):
        local = self._turn(session, turn_id)
        binding = self.store.one("SELECT * FROM sessions WHERE id=?", (session.id,))
        inp = upstream.get("input", {})
        if (
            upstream.get("id") != (local["bridge_request_id"] or self._request_id(turn_id))
            or inp.get("message") != local["prompt"].strip()
            or inp.get("sourceClientId") != binding["bridge_client_id"]
            or inp.get("sessionId", "") != (binding["bridge_session_id"] or "")
            or inp.get("model", "") != ""
            or inp.get("effort", "") != ""
            or inp.get("metadata", {}).get("requiredModel") != binding["bridge_model"]
            or inp.get("metadata", {}).get("requiredEffort") != (binding["bridge_effort"] or "")
            or inp.get("metadata", {}).get("researchNodeId") != session.node_id
        ):
            self._uncertain(
                turn_id, "UNCERTAIN: stored Bridge request differs from its local turn or binding"
            )
            raise TransportError(
                "UNCERTAIN: stored Bridge request does not match the exact local turn and binding"
            )

    async def acknowledge_not_submitted(self, session, turn_id):
        """Explicitly release a proven composer-preparation failure, never resend it.

        Absence of Send confirmation is insufficient. Both the authoritative
        failed turn and its source cancellation must prove that preparation
        stopped before entering the submission boundary.
        """
        async with self._locks.setdefault(session.id, asyncio.Lock()):
            local = self._turn(session, turn_id)
            if local["status"] == "FAILED_NOT_SENT":
                return {"turn_id": turn_id, "status": "FAILED_NOT_SENT"}
            if (
                local["status"] != "ERROR"
                or local["raw_response"] is not None
                or not local["bridge_request_id"]
            ):
                raise TransportError("Only a terminal composer error can be explicitly released")
            request_id = local["bridge_request_id"]
            path = "/turns/" + quote(request_id, safe="")
            upstream = (await self._json("GET", path)).get("turn", {})
            self._validate_upstream(upstream, session, turn_id)

            def proven(value):
                return (
                    value.get("code") == "COMPOSER_TEXT_VERIFY_FAILED"
                    and value.get("provenNotExecuted") is True
                    and value.get("cancellationEvidence")
                    == {
                        "source": "composer_preparation",
                        "reason": "submission_boundary_not_entered",
                    }
                )

            if (
                upstream.get("status") != "failed"
                or upstream.get("output") is not None
                or not proven(upstream.get("error") or {})
            ):
                raise TransportError("Terminal error does not positively prove NOT_SENT")
            events = (await self._json("GET", path + "/events", params={"limit": 5000})).get(
                "events"
            )
            if (
                not isinstance(events, list)
                or not events
                or len(events) >= 5000
                or events[0].get("type") != "turn/queued"
                or events[-1].get("type") != "turn/failed"
            ):
                raise TransportError("Incomplete terminal evidence cannot prove NOT_SENT")
            source_proof = False
            client_id = self.store.one(
                "SELECT bridge_client_id FROM sessions WHERE id=?", (session.id,)
            )["bridge_client_id"]
            for event in events:
                data = event.get("data") or {}
                payload = data.get("payload") or data
                for item in (data, payload):
                    if (
                        item.get("requestId", request_id) != request_id
                        or item.get("turnId", request_id) != request_id
                    ):
                        raise TransportError("NOT_SENT evidence belongs to another request")
                    if item.get("clientId", client_id) != client_id:
                        raise TransportError(
                            "NOT_SENT source evidence belongs to another browser tab"
                        )
                if event.get("type") in {
                    "prompt.submitted",
                    "prompt.sent",
                    "request.done",
                    "diagnostic.prompt.submit.attempt",
                    "diagnostic.prompt.submit.already_confirmed",
                    "diagnostic.chat.prompt.submit.confirmed",
                    "chat.prompt.submit.confirmed",
                }:
                    raise TransportError(
                        "A Send attempt or submitted turn prevents NOT_SENT release"
                    )
                if event.get("type") in {
                    "request.effect.cancelled",
                    "diagnostic.request.effect.cancelled",
                }:
                    source_proof |= payload.get("effectType") == "prompt.submit" and proven(payload)
            terminal = events[-1].get("data", {}).get("turn") or {}
            if (
                not source_proof
                or terminal.get("id") != request_id
                or terminal.get("status") != "failed"
                or not proven(terminal.get("error") or {})
            ):
                raise TransportError(
                    "Source cancellation and terminal record do not prove NOT_SENT"
                )
            self._validate_upstream(terminal, session, turn_id)
            with self.store.transaction() as c:
                changed = c.execute(
                    "UPDATE turns SET status='FAILED_NOT_SENT' WHERE id=? AND status='ERROR' AND raw_response IS NULL",
                    (turn_id,),
                )
                if changed.rowcount != 1:
                    raise TransportError("Turn changed while acknowledging NOT_SENT")
                self.store.event(
                    "bridge_not_submitted_acknowledged",
                    {
                        "turn_id": turn_id,
                        "request_id": request_id,
                        "turn": upstream,
                        "events": events,
                    },
                    c,
                )
            return {"turn_id": turn_id, "request_id": request_id, "status": "FAILED_NOT_SENT"}

    async def _reconcile(self, session, turn_id):
        local = self._turn(session, turn_id)
        if local["status"] == "FAILED_NOT_SENT":
            raise TransportError(
                "This undelivered failure is closed; use a new approved turn identity"
            )
        if (local["error"] or "").startswith("MODEL_UNVERIFIED:"):
            # Restoring today's picker cannot prove which model generated an
            # earlier reply. Only an explicit human reconciliation may release it.
            raise TransportError(local["error"])
        request_id = local["bridge_request_id"] or self._request_id(turn_id)
        try:
            result = await self._json("GET", "/turns/" + quote(request_id, safe=""))
        except TransportError as exc:
            self._uncertain(
                turn_id,
                "UNCERTAIN: durable Bridge turn could not be queried; no automatic resend. Inspect Bridge diagnostics.",
            )
            raise TransportError(self._turn(session, turn_id)["error"]) from exc
        upstream = result.get("turn", {})
        self._validate_upstream(upstream, session, turn_id)
        self.store.execute(
            "UPDATE turns SET bridge_request_id=?,status='SENT',error=NULL WHERE id=? AND raw_response IS NULL",
            (request_id, turn_id),
        )
        return upstream

    async def _terminal(self, session, turn_id, upstream):
        status = upstream.get("status")
        if status in {"failed", "interrupted", "cancelled"}:
            detail = upstream.get("error") or {}
            message = f"Bridge terminal error {detail.get('code', status)}: {detail.get('message', status)}"
            self.store.execute(
                "UPDATE turns SET status='ERROR',error=? WHERE id=?", (message, turn_id)
            )
            raise TransportError(message)
        if status not in {"completed", "completed_without_artifact"}:
            return None
        response = (upstream.get("output") or {}).get("response") or {}
        raw = response.get("answer")
        if (
            not isinstance(raw, str)
            or not raw.strip()
            or response.get("requestId", response.get("id")) != upstream["id"]
        ):
            raise TransportError(
                "Bridge terminal record lacks a complete authoritative response for this request"
            )
        # Preserve every completed attempted reply even if its binding or model
        # proof fails. Unverified text must not enter raw_response/_request.
        self.store.event(
            "bridge_terminal_observed",
            {
                "turn_id": turn_id,
                "node_id": session.node_id,
                "bridge_request_id": upstream["id"],
                "response": response,
            },
        )
        row = self.store.one("SELECT * FROM sessions WHERE id=?", (session.id,))
        conversation = (response.get("session") or {}).get("id")
        url = (response.get("session") or {}).get("url") or response.get("url")
        if (
            not conversation
            or conversation == "new"
            or not url
            or _url_conversation(url) != conversation
        ):
            raise TransportError(
                "Bridge terminal result does not prove a persistent ChatGPT conversation URL"
            )
        if response.get("sourceClientId") != row["bridge_client_id"] or (
            row["bridge_session_id"] and row["bridge_session_id"] != conversation
        ):
            raise TransportError("Bridge terminal response belongs to another tab or conversation")
        try:
            _, model, effort = await self._selection(session)
            if model != row["bridge_model"] or effort != (row["bridge_effort"] or ""):
                raise TransportError(
                    "MODEL_UNAVAILABLE: bound tab selection changed during the outstanding turn"
                )
        except TransportError as exc:
            message = (
                "UNCERTAIN: bridge model/effort proof could not be re-read; retry querying the same durable turn after reconnecting."
                if str(exc).startswith("Bridge request failed:")
                else "MODEL_UNVERIFIED: browser model/effort changed or cannot be verified for this completed attempt. Manual reconciliation is required; restoring the picker cannot release this reply."
            )
            self._uncertain(turn_id, message)
            raise TransportError(self._turn(session, turn_id)["error"]) from exc
        with self.store.transaction() as c:
            c.execute(
                "UPDATE sessions SET bridge_session_id=?,url=? WHERE id=?",
                (conversation, url, session.id),
            )
            c.execute(
                "UPDATE turns SET raw_response=?,status='COMPLETED',error=NULL WHERE id=?",
                (raw, turn_id),
            )
        self._completed_roles.add(session.model)
        self._health["live_verified"] = (
            len(self._completed_roles) == 2 and self._http_transport is None
        )
        return raw

    async def await_response(self, session, turn_id):
        async with self._locks.setdefault(session.id, asyncio.Lock()):
            local = self._turn(session, turn_id)
            if local["raw_response"] is not None:
                return str(local["raw_response"])
            upstream = await self._reconcile(session, turn_id)
            result = await self._terminal(session, turn_id, upstream)
            if result is not None:
                return result
            request_id = upstream["id"]
            try:
                async with asyncio.timeout(self.config.bridge_turn_timeout):
                    async with self._client() as client:
                        async with client.stream(
                            "GET",
                            f"/turns/{quote(request_id, safe='')}/events",
                            params={"stream": "1"},
                            timeout=self.config.bridge_turn_timeout,
                        ) as response:
                            response.raise_for_status()
                            async for event in _sse(response):
                                # Ignore previews and events for other requests.
                                if event.get("turnId") not in {None, request_id}:
                                    continue
                                if (
                                    event.get("type")
                                    in {
                                        "request.result",
                                        "request.error",
                                        "turn/completed",
                                        "turn/completed_without_artifact",
                                        "turn/failed",
                                        "turn/interrupted",
                                        "turn/cancelled",
                                    }
                                    or event.get("_sse_event") == "done"
                                ):
                                    terminal = await self._reconcile(session, turn_id)
                                    result = await self._terminal(session, turn_id, terminal)
                                    if result is not None:
                                        return result
            except (httpx.HTTPError, TimeoutError) as exc:
                self._health.update(
                    available=False,
                    autonomous=False,
                    detail="Bridge response disconnected or timed out; durable turn retained for recovery.",
                )
                raise TransportError(self._health["detail"]) from exc
            raise TransportError(
                "Bridge stream ended before the authoritative terminal result; recover this same turn."
            )


async def _sse(response):
    lines, event_name = [], "message"
    async for line in response.aiter_lines():
        if not line:
            if lines:
                try:
                    event = json.loads("\n".join(lines))
                except ValueError as exc:
                    raise TransportError("Bridge emitted invalid SSE JSON") from exc
                if isinstance(event, dict):
                    yield {**event, "_sse_event": event_name}
            lines, event_name = [], "message"
        elif line.startswith("data:"):
            lines.append(line[5:].lstrip(" "))
        elif line.startswith("event:"):
            event_name = line[6:].strip()


def _compatible(client):
    return bool(
        client.get("id")
        and client.get("ready", True)
        and client.get("compatible", True)
        and client.get("compatibility", {}).get("compatible", True)
    )


def _url_conversation(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"chatgpt.com", "chat.openai.com"}:
        return None
    return parsed.path.split("/c/", 1)[1].strip("/") if "/c/" in parsed.path else None


def _conversation(client):
    return _url_conversation(client.get("url", "")) or _url_conversation(
        (client.get("session") or {}).get("url", "")
    )


def _norm(value):
    return " ".join(str(value).casefold().replace("‑", "-").split())


def _option(options, expected):
    return next(
        (
            o
            for o in options
            if any(_norm(o.get(k, "")) == _norm(expected) for k in ("id", "value", "label"))
        ),
        None,
    )


def _same(current, wanted):
    return bool(
        current
        and wanted
        and any(
            current.get(k) and current.get(k) == wanted.get(k) for k in ("id", "value", "label")
        )
    )


def _role_model(option, role):
    label = _norm(option.get("label", ""))
    return label == "gpt-6 pro" if role == PRO_MODEL else label in {"gpt-6 thinking", "gpt-6"}


def _configured_model(options, expected, role):
    direct = _option(options, expected)
    if direct and _role_model(direct, role):
        return direct
    # These are the same GPT-6 family across two observed picker layouts.
    # Pro intelligence is separately required below; GPT-5.6 + Pro is refused.
    aliases = {"gpt-6 pro"} if role == PRO_MODEL else {"gpt-6", "gpt-6 thinking"}
    if _norm(expected) in aliases:
        return next((o for o in options if _norm(o.get("label", "")) == "gpt-6"), None)
    return None


def _pro_effort(option):
    return _norm(option.get("label", "")) == "pro"


def _extra_high(option):
    return any(
        _norm(option.get(k, "")) in {"xhigh", "extra high", "extra-high"}
        for k in ("id", "value", "label")
    )
