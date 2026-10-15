"""Task-local lease context, shared by persistence services without global mutable owners."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_GUARD: ContextVar[Callable[..., None] | None] = ContextVar("research_job_guard", default=None)
_METADATA: ContextVar[dict[str, str] | None] = ContextVar("research_job_metadata", default=None)


@contextmanager
def execution_scope(guard: Callable[..., None], metadata: dict[str, str]) -> Iterator[None]:
    guard_token = _GUARD.set(guard)
    metadata_token = _METADATA.set(metadata)
    try:
        yield
    finally:
        _METADATA.reset(metadata_token)
        _GUARD.reset(guard_token)


def check_owner(connection: sqlite3.Connection | None = None) -> None:
    guard = _GUARD.get()
    if guard is not None:
        guard(connection)


def run_metadata() -> dict[str, str]:
    return dict(_METADATA.get() or {})
