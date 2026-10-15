"""Persistent jobs with fencing tokens, heartbeat and explicit failed-job recovery."""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from .db import Database


class JobUnavailableError(ValueError):
    """The requested job did not execute because it is not currently claimable."""


class LeaseLostError(RuntimeError):
    """A stale execution lost authority to publish state."""


class JobStore:
    def __init__(self, db: Database, lease_seconds: float = 900, max_attempts: int = 3):
        self.db, self.lease_seconds, self.max_attempts = db, lease_seconds, max_attempts

    def enqueue(self, kind: str, scope_type: str, scope_id: str, priority: int = 0) -> int:
        with self.db.transaction() as c:
            row = c.execute(
                "SELECT id FROM jobs WHERE job_type=? AND scope_type=? AND scope_id=?",
                (kind, scope_type, scope_id),
            ).fetchone()
            if row:
                return row["id"]
            return c.execute(
                "INSERT INTO jobs(job_type,scope_type,scope_id,max_attempts,priority) "
                "VALUES(?,?,?,?,?)",
                (kind, scope_type, scope_id, self.max_attempts, priority),
            ).lastrowid

    def claim(self, job_id: int, max_concurrent: int | None = None) -> str | None:
        with self.db.transaction() as c:
            row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row or row["status"] != "QUEUED" or row["attempts"] >= row["max_attempts"]:
                return None
            if max_concurrent is not None:
                running = c.execute(
                    "SELECT COUNT(*) FROM jobs WHERE job_type='RUN_BRANCH' AND status='RUNNING'"
                ).fetchone()[0]
                if running >= max_concurrent:
                    return None
            token = uuid4().hex
            c.execute(
                "UPDATE jobs SET status='RUNNING',attempts=attempts+1,lease_owner=?,lease_expires_at=?,"
                "started_at=CURRENT_TIMESTAMP,error=NULL WHERE id=?",
                (token, time.time() + self.lease_seconds, job_id),
            )
            return token

    def assert_owner(
        self, job_id: int, owner: str, connection: sqlite3.Connection | None = None
    ) -> None:
        row = (
            connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if connection is not None
            else self.db.one("SELECT * FROM jobs WHERE id=?", (job_id,))
        )
        if (
            not row
            or row["status"] != "RUNNING"
            or row["lease_owner"] != owner
            or row["lease_expires_at"] is None
            or row["lease_expires_at"] < time.time()
        ):
            raise LeaseLostError("Job lease lost; stale execution cannot commit")

    def complete(self, job_id: int, owner: str) -> None:
        with self.db.transaction() as connection:
            self.assert_owner(job_id, owner, connection)
            connection.execute(
                "UPDATE jobs SET status='COMPLETED',completed_at=CURRENT_TIMESTAMP,"
                "lease_owner=NULL,lease_expires_at=NULL WHERE id=? AND lease_owner=?",
                (job_id, owner),
            )

    def fail(
        self,
        job_id: int,
        owner: str,
        error: BaseException,
        connection: sqlite3.Connection | None = None,
    ) -> bool:
        if connection is None:
            with self.db.transaction() as connection:
                return self.fail(job_id, owner, error, connection)
        # Store only exception class; external error text can contain credentials.
        changed = connection.execute(
            "UPDATE jobs SET status='FAILED',error=?,lease_owner=NULL,lease_expires_at=NULL "
            "WHERE id=? AND lease_owner=? AND status='RUNNING' AND lease_expires_at>=?",
            (type(error).__name__, job_id, owner, time.time()),
        )
        return changed.rowcount == 1

    def recover(self) -> int:
        with self.db.transaction() as c:
            rows = c.execute(
                "SELECT id FROM jobs WHERE status='RUNNING' AND lease_expires_at<?", (time.time(),)
            ).fetchall()
            c.execute(
                "UPDATE jobs SET status=CASE WHEN attempts<max_attempts THEN 'QUEUED' ELSE 'FAILED' END,"
                "lease_owner=NULL,lease_expires_at=NULL,error='ExpiredLease' "
                "WHERE status='RUNNING' AND lease_expires_at<?",
                (time.time(),),
            )
            return len(rows)

    def retry(self, job_id: int) -> None:
        with self.db.transaction() as c:
            row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row or row["status"] != "FAILED":
                raise ValueError("Only failed infrastructure jobs can be retried")
            # An explicit operator retry grants a fresh bounded attempt window.
            c.execute(
                "UPDATE jobs SET status='QUEUED',max_attempts=attempts+?,error=NULL WHERE id=?",
                (self.max_attempts, job_id),
            )
            if row["job_type"] == "BRAIN":
                c.execute(
                    "UPDATE brain_cycles SET status='PENDING' WHERE id=? AND status='FAILED'",
                    (row["scope_id"],),
                )

    @asynccontextmanager
    async def heartbeat(self, job_id: int, owner: str) -> AsyncIterator[None]:
        parent = asyncio.current_task()
        lost = False

        async def renew() -> None:
            nonlocal lost
            while True:
                await asyncio.sleep(self.lease_seconds / 3)
                try:
                    with self.db.transaction() as connection:
                        self.assert_owner(job_id, owner, connection)
                        connection.execute(
                            "UPDATE jobs SET lease_expires_at=? WHERE id=? AND lease_owner=?",
                            (time.time() + self.lease_seconds, job_id, owner),
                        )
                except Exception:
                    lost = True
                    if parent:
                        parent.cancel()
                    return

        task = asyncio.create_task(renew())
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            if lost:
                raise LeaseLostError("Job lease lost during execution")
