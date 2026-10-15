"""Serve the ordinary bridge-provider review UI without a scheduler worker.

This isolated handoff never calls run/tick/diagnose or binds a model session.
Human actions use the application's unchanged durable review endpoints.
"""

import asyncio
import json
import os
from pathlib import Path

from math_research_agent.dashboard import Dashboard
from math_research_agent.scheduler import Scheduler
from math_research_agent.store import Store


async def main():
    project = Path(__file__).parent / "runs/human_review/project"
    scheduler = Scheduler(Store(project))
    if scheduler.store.config.transport != "bridge" or not scheduler.store.setting(
        "manual_review_enabled"
    ):
        raise ValueError("This handoff requires the real bridge provider and manual review ON")
    dashboard = Dashboard(scheduler)
    server = await asyncio.start_server(dashboard.handle, "127.0.0.1", 8767)
    print(
        json.dumps(
            {
                "pid": os.getpid(),
                "url": "http://127.0.0.1:8767/",
                "scheduler_worker_running": False,
                "project": str(project),
            }
        ),
        flush=True,
    )
    try:
        async with server:
            await server.serve_forever()
    finally:
        await scheduler.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
