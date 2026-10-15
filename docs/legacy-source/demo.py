"""Offline demonstration through the same scheduler used by the dashboard."""

from __future__ import annotations

from pathlib import Path

from .config import Config
from .paths import project_root
from .scheduler import Scheduler
from .store import Store


async def run_offline_demo(
    projects_root: Path, slug: str = "research-tree-demo", rounds: int = 2
) -> Path:
    root = project_root(projects_root, slug)
    config = Config(projects_root=projects_root, transport="fake", manual_review_enabled=False)
    store = Store.initialize(
        root,
        "For real x, prove that x squared is nonnegative and identify the equality case. "
        "In later rounds independently check the argument and its assumptions.",
        config,
    )
    await Scheduler(store).run(max_rounds=rounds)
    return root
