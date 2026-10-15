"""Bounded workers. A failed branch never cancels its siblings."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .jobs import JobUnavailableError

logger = logging.getLogger(__name__)


async def run_workers(app: Any, max_concurrent: int | None = None) -> list[dict]:
    limit = app.config.limits.max_concurrent_branches if max_concurrent is None else max_concurrent
    if limit < 1 or limit > app.config.limits.max_concurrent_branches:
        raise ValueError("Worker concurrency must be positive and within configured limit")
    app.jobs.recover()
    rows = app.db.query(
        "SELECT * FROM jobs WHERE job_type='RUN_BRANCH' AND status='QUEUED' ORDER BY priority DESC,id"
    )
    semaphore = asyncio.Semaphore(limit)

    async def worker(row: dict) -> dict:
        async with semaphore:
            try:
                result = await app.execute_job(row["id"], max_concurrent=limit)
                return {"job": row["id"], "result": result, "error": None}
            except JobUnavailableError:
                return {"job": row["id"], "result": None, "error": None, "deferred": True}
            except Exception as exc:
                logger.error(
                    "project=%s role=worker branch=%s job=%s error=%s",
                    app.db.project["slug"],
                    row["scope_id"],
                    row["id"],
                    type(exc).__name__,
                )
                return {"job": row["id"], "result": None, "error": type(exc).__name__}

    return await asyncio.gather(*(worker(row) for row in rows))
