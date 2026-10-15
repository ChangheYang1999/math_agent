"""Local-only dashboard; the HTTP server and scheduler share one asyncio loop."""

from __future__ import annotations

import asyncio
import contextlib
import json
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .scheduler import Scheduler

PAGE = Path(__file__).with_name("static") / "dashboard.html"
REVIEW_RECORD = (
    "SELECT a.id,a.node_id,a.round_id,a.artifact_type,a.version,a.content_hash,"
    "a.status,a.decision,a.decided_at,r.stage AS round_stage "
    "FROM approvals a JOIN rounds r ON r.id=a.round_id "
)


def review_record(row):
    record = dict(row)
    record["approval_source"] = (
        "HUMAN_APPROVED" if record["status"] == "APPROVED" else record["status"]
    )
    record["execution_status"] = {
        "PROMPT_READY": "WAITING_FOR_DISPATCH",
        "SOLVING": "LEAF_RUNNING",
        "REPORT_APPROVAL": "WAITING_FOR_REPORT_APPROVAL",
        "AWAITING_PARENT_RESPONSE": "WAITING_FOR_PARENT_RESPONSE",
        "RESPONDED": "PARENT_RESPONSE_SAVED",
    }.get(record["round_stage"], record["round_stage"])
    return record


class Dashboard:
    def __init__(self, scheduler: Scheduler):
        self.scheduler = scheduler
        self.runtime_error: str | None = None

    def snapshot(self) -> dict:
        state = self.scheduler.snapshot()
        transport = self.scheduler.transport
        state["transport_health"] = transport.health()
        if hasattr(transport, "list_pending"):
            state["relay_pending"] = transport.list_pending()
        else:
            state["relay_pending"] = []
        state["runtime_error"] = self.runtime_error
        state["project_name"] = self.scheduler.store.root.name
        state["review_history"] = [
            review_record(row)
            for row in self.scheduler.store.query(
                REVIEW_RECORD
                + "WHERE a.status='APPROVED' ORDER BY a.decided_at DESC,a.id DESC LIMIT 20"
            )
        ]
        return state

    def mutate(self, path: str, body: dict) -> dict:
        scheduler = self.scheduler
        if path == "/api/project":
            status = body.get("status")
            if status not in {"ACTIVE", "PAUSED"}:
                raise ValueError("Project status must be ACTIVE or PAUSED")
            scheduler.store.set_setting("project_status", status)
        elif path == "/api/review-mode":
            if not isinstance(body.get("enabled"), bool):
                raise ValueError("enabled must be a boolean")
            scheduler.set_review_mode(body["enabled"])
        elif path == "/api/decision":
            previous = scheduler.store.one(
                "SELECT status FROM approvals WHERE id=?", (body["approval_id"],)
            )
            scheduler.decide(
                body["approval_id"], body["decision"], body["content_hash"], body.get("comment", "")
            )
            return {
                "ok": True,
                "decision": body["decision"],
                "duplicate": bool(previous and previous["status"] == "APPROVED"),
                "approval": review_record(
                    scheduler.store.one(REVIEW_RECORD + "WHERE a.id=?", (body["approval_id"],))
                ),
            }
        elif path == "/api/review-message":
            message_id = scheduler.ask_parent(
                body["approval_id"], body["content_hash"], body.get("comment", "")
            )
            return {"ok": True, "message_id": message_id}
        elif path == "/api/recover":
            return scheduler.recover()
        elif path == "/api/relay/bind":
            scheduler.transport.bind_session(body["session_id"], body["url"], body["model"])
        elif path == "/api/relay/sent":
            scheduler.transport.mark_sent(body["turn_id"])
        elif path == "/api/relay/response":
            raw = body.get("raw_response", "")
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError("Paste the actual, complete ChatGPT response")
            scheduler.transport.submit_response(body["turn_id"], raw)
        else:
            raise ValueError("Unknown action")
        return {"ok": True}

    async def act(self, path: str, body: dict) -> dict:
        if path == "/api/diagnose":
            transport = self.scheduler.transport
            result = (
                await transport.diagnose() if hasattr(transport, "diagnose") else transport.health()
            )
            return {"ok": True, "diagnostic": result}
        return self.mutate(path, body)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        status, kind, content = 200, "application/json; charset=utf-8", b""
        try:
            headers = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=10)
            lines = headers.decode("iso-8859-1").split("\r\n")
            method, target, _ = lines[0].split(" ", 2)
            fields = dict(line.split(":", 1) for line in lines[1:] if ":" in line)
            fields = {key.strip().lower(): value.strip() for key, value in fields.items()}
            length = int(fields.get("content-length", "0"))
            if length < 0 or length > 4 * 1024 * 1024:
                raise ValueError("Request body exceeds 4 MiB")
            target_url = urlsplit(target)
            path = target_url.path
            if method == "GET" and path == "/":
                kind, content = "text/html; charset=utf-8", PAGE.read_bytes()
            elif method == "GET" and path == "/api/state":
                content = json.dumps(self.snapshot(), ensure_ascii=False, default=str).encode()
            elif method == "GET" and path == "/report":
                report = self.scheduler.store.root / "RESEARCH_REPORT.md"
                kind = "text/plain; charset=utf-8"
                content = (
                    report.read_bytes()
                    if report.exists()
                    else b"No significant findings published yet.\n"
                )
            elif method == "GET" and path == "/review-original":
                approval_id = parse_qs(target_url.query).get("id", [""])[0]
                artifact = self.scheduler.store.one(
                    "SELECT payload FROM approvals WHERE id=?", (approval_id,)
                )
                if not artifact:
                    raise ValueError("Unknown approval item")
                kind = "text/plain; charset=utf-8"
                content = artifact["payload"].encode("utf-8")
            elif method == "POST" and path.startswith("/api/"):
                origin = fields.get("origin")
                if origin and origin != f"http://{fields.get('host', '')}":
                    raise ValueError("Local dashboard actions require the same origin")
                body = json.loads(await asyncio.wait_for(reader.readexactly(length), timeout=10))
                if not isinstance(body, dict):
                    raise ValueError("Expected a JSON object")
                content = json.dumps(
                    await self.act(path, body), ensure_ascii=False, default=str
                ).encode()
            else:
                status, content = 404, b'{"error":"Not found"}'
        except (ValueError, KeyError, AttributeError, RuntimeError, OSError) as exc:
            status = 400
            content = json.dumps({"error": str(exc)}, ensure_ascii=False).encode()
        except (TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            status, content = 400, b'{"error":"Incomplete HTTP request"}'
        except Exception as exc:
            status = 500
            content = json.dumps({"error": str(exc)}, ensure_ascii=False).encode()
        reason = {200: "OK", 400: "Bad Request", 404: "Not Found", 500: "Internal Server Error"}[
            status
        ]
        writer.write(
            f"HTTP/1.1 {status} {reason}\r\nContent-Type: {kind}\r\n"
            f"Content-Length: {len(content)}\r\nCache-Control: no-store\r\n"
            "Connection: close\r\n\r\n".encode()
            + content
        )
        with contextlib.suppress(ConnectionError):
            await writer.drain()
        writer.close()
        with contextlib.suppress(ConnectionError):
            await writer.wait_closed()


async def serve(scheduler: Scheduler, port: int = 8765, open_browser: bool = False) -> None:
    dashboard = Dashboard(scheduler)
    server = await asyncio.start_server(dashboard.handle, "127.0.0.1", port)

    async def run_scheduler() -> None:
        try:
            await scheduler.run()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            dashboard.runtime_error = str(exc)

    runner = asyncio.create_task(run_scheduler())
    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{port}")
    try:
        async with server:
            await server.serve_forever()
    finally:
        runner.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await runner
        await scheduler.aclose()
