import time

import pytest

from math_research_agent.db import Database
from math_research_agent.jobs import JobStore


def test_job_claim_cap_lease_recovery_and_explicit_retry(tmp_path):
    db = Database.initialize(tmp_path, "test", "Test")
    store = JobStore(db, lease_seconds=60, max_attempts=3)
    a = store.enqueue("RUN_BRANCH", "branch", "B-000001")
    b = store.enqueue("RUN_BRANCH", "branch", "B-000002")
    assert store.enqueue("RUN_BRANCH", "branch", "B-000001") == a
    owner = store.claim(a, max_concurrent=1)
    assert owner
    assert store.claim(a, max_concurrent=1) is None
    assert store.claim(b, max_concurrent=1) is None
    db.execute("UPDATE jobs SET lease_expires_at=? WHERE id=?", (time.time() - 1, a))
    assert store.recover() == 1
    replacement = store.claim(a, max_concurrent=1)
    assert replacement != owner
    with pytest.raises(RuntimeError, match="lease"):
        store.complete(a, owner)
    store.fail(a, replacement, RuntimeError("network"))
    assert db.one("SELECT status FROM jobs WHERE id=?", (a,))["status"] == "FAILED"
    store.retry(a)
    assert store.claim(a, max_concurrent=1)


async def test_heartbeat_renews_running_job(tmp_path):
    import asyncio

    db = Database.initialize(tmp_path, "test", "Test")
    store = JobStore(db, lease_seconds=0.1, max_attempts=3)
    job = store.enqueue("BACKGROUND", "project", "1")
    owner = store.claim(job)
    async with store.heartbeat(job, owner):
        await asyncio.sleep(0.15)
        assert store.recover() == 0
    store.complete(job, owner)
